"""Poll USGS continuous observations and upsert them into Tiger Data."""

import logging
import math
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections"
PARAMETERS = (
    "32319", "32316", "00300", "00400", "00010", "00671",
    "00631", "00608", "00060", "63680", "00095",
)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    station: str = "USGS-040851385"
    poll_seconds: int = 300
    overlap_hours: int = 6
    enabled: bool = True

    @classmethod
    def from_env(cls):
        database_url = (
            os.getenv("TIGER_DATABASE_URL", "").strip()
            or os.getenv("INGEST_DATABASE_URL", "").strip()
            or os.getenv("TIMESCALE_SERVICE_URL", "").strip()
        )
        settings = cls(
            database_url=database_url,
            api_key=os.getenv("USGS_API_KEY", ""),
            station=os.getenv("USGS_STATION_ID", "USGS-040851385"),
            poll_seconds=int(os.getenv("USGS_POLL_SECONDS", "300")),
            overlap_hours=int(os.getenv("USGS_OVERLAP_HOURS", "6")),
            enabled=os.getenv("USGS_INGESTION_ENABLED", "true").lower() == "true",
        )
        if settings.poll_seconds < 60 or not 1 <= settings.overlap_hours <= 24:
            raise ValueError("Poll interval must be >=60 seconds; overlap must be 1-24 hours")
        return settings


def utcnow():
    return datetime.now(timezone.utc)


def fetch_features(client, collection, station, start=None, end=None):
    params = {"f": "json", "monitoring_location_id": station, "limit": 1000}
    if start is not None:
        params["datetime"] = f"{start.isoformat()}/{end.isoformat()}"
    url = f"{BASE_URL}/{collection}/items"
    seen = set()
    for _ in range(100):
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
            raise ValueError("Unexpected USGS response")
        yield from payload["features"]
        next_link = next((link["href"] for link in payload.get("links", []) if link.get("rel") == "next"), None)
        if not next_link:
            return
        url = urljoin(str(response.url), next_link)
        # Never forward the API key to an unrelated pagination host.
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.waterdata.usgs.gov" or url in seen:
            raise ValueError("Invalid USGS pagination link")
        seen.add(url)
        params = None
    raise ValueError("USGS pagination exceeded the per-poll limit")


def observation_row(feature, station):
    p = feature["properties"]
    if p["monitoring_location_id"] != station or p["parameter_code"] not in PARAMETERS:
        return None
    observed_at = datetime.fromisoformat(p["time"].replace("Z", "+00:00"))
    if observed_at.tzinfo is None:
        raise ValueError("USGS observation has no timezone")
    # Preserve nonnumeric/missing readings as NULL, with their raw metadata.
    try:
        value = float(p["value"])
        if not math.isfinite(value):
            value = None
    except (TypeError, ValueError):
        value = None
    return (
        observed_at, p["time_series_id"], station, p["parameter_code"],
        value, p.get("unit_of_measure"), p.get("approval_status"), Jsonb(p),
    )


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS usgs_observations (
        observed_at TIMESTAMPTZ NOT NULL,
        time_series_id TEXT NOT NULL,
        station_id TEXT NOT NULL,
        parameter_code TEXT NOT NULL,
        value DOUBLE PRECISION,
        unit TEXT,
        approval_status TEXT,
        source JSONB NOT NULL,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (time_series_id, observed_at)
    )""",
    "SELECT create_hypertable('usgs_observations', by_range('observed_at'), if_not_exists => TRUE)",
    """CREATE INDEX IF NOT EXISTS usgs_station_parameter_time
       ON usgs_observations (station_id, parameter_code, observed_at DESC)""",
    """CREATE TABLE IF NOT EXISTS usgs_ingestion_checkpoints (
        station_id TEXT PRIMARY KEY, through_time TIMESTAMPTZ NOT NULL
    )""",
)
UPSERT = """INSERT INTO usgs_observations
    (observed_at, time_series_id, station_id, parameter_code, value, unit, approval_status, source)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (time_series_id, observed_at) DO UPDATE SET
        value = EXCLUDED.value, unit = EXCLUDED.unit,
        approval_status = EXCLUDED.approval_status, source = EXCLUDED.source,
        ingested_at = now()
    WHERE usgs_observations.source IS DISTINCT FROM EXCLUDED.source
"""


class Collector:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.status = {
            "configured": bool(settings.database_url),
            "enabled": settings.enabled,
            "station_id": settings.station,
            "requested_parameters": list(PARAMETERS),
            "poll_seconds": settings.poll_seconds,
            "running": False,
            "last_success": None,
            "last_error": None,
        }

    def client(self):
        headers = {"X-Api-Key": self.settings.api_key} if self.settings.api_key else {}
        return httpx.Client(headers=headers, timeout=30)

    def latest(self):
        with self.client() as client:
            features = list(fetch_features(client, "latest-continuous", self.settings.station))
        readings = [f["properties"] for f in features if observation_row(f, self.settings.station) is not None]
        available = {p["parameter_code"] for p in readings}
        return {
            "station_id": self.settings.station,
            "readings": readings,
            "missing_parameters": sorted(set(PARAMETERS) - available),
        }

    def stored_latest(self):
        """Read the newest observation per parameter exclusively from Tiger Data."""
        with psycopg.connect(self.settings.database_url, connect_timeout=10,
                             options="-c statement_timeout=10000 -c default_transaction_read_only=on",
                             row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""SELECT DISTINCT ON (parameter_code)
                        parameter_code, time_series_id, observed_at, value, unit,
                        approval_status, source->>'qualifier' AS qualifier, ingested_at
                    FROM usgs_observations
                    WHERE station_id = %s AND parameter_code = ANY(%s)
                    ORDER BY parameter_code, observed_at DESC, time_series_id ASC""",
                    (self.settings.station, list(PARAMETERS)))
                readings = cursor.fetchall()
        available = {row["parameter_code"] for row in readings}
        return {
            "source": "tiger_data",
            "station_id": self.settings.station,
            "requested_parameters": list(PARAMETERS),
            "readings": readings,
            "missing_parameters": sorted(set(PARAMETERS) - available),
            "fetched_at": utcnow(),
            "stale_after_seconds": 1800,
        }

    def poll(self):
        if not self.settings.database_url:
            raise RuntimeError("Set TIGER_DATABASE_URL to enable database ingestion")
        if not self.lock.acquire(blocking=False):
            return {"skipped": "A poll is already running"}
        self.status["running"] = True
        try:
            result = self._poll()
            if "skipped" not in result:
                self.status.update(result, last_success=utcnow().isoformat(), last_error=None)
            return result
        except Exception as exc:
            # Exception text can contain connection credentials or API keys.
            self.status["last_error"] = type(exc).__name__
            LOGGER.error("USGS ingestion failed (%s); retrying on the next poll", type(exc).__name__)
            raise
        finally:
            self.status["running"] = False
            self.lock.release()

    def _poll(self):
        with psycopg.connect(self.settings.database_url, connect_timeout=10,
                             options="-c statement_timeout=30000") as conn:
            with conn.cursor() as cursor:
                # Transaction-scoped lock also protects against multiple API workers.
                cursor.execute("SELECT pg_try_advisory_xact_lock(748392061)")
                if not cursor.fetchone()[0]:
                    return {"skipped": "Another worker is ingesting"}
                for statement in SCHEMA:
                    cursor.execute(statement)
                cursor.execute("SELECT through_time FROM usgs_ingestion_checkpoints WHERE station_id = %s",
                               (self.settings.station,))
                checkpoint = cursor.fetchone()
                now = utcnow()
                through = checkpoint[0] if checkpoint else now - timedelta(hours=24)
                start = through - timedelta(hours=self.settings.overlap_hours) if checkpoint else through
                # Catch up in bounded daily chunks; commit progress only with observations.
                end = min(now, through + timedelta(days=1))
                with self.client() as client:
                    rows = [row for feature in fetch_features(client, "continuous", self.settings.station, start, end)
                            if (row := observation_row(feature, self.settings.station)) is not None]
                if rows:
                    cursor.executemany(UPSERT, rows)
                cursor.execute("""INSERT INTO usgs_ingestion_checkpoints VALUES (%s, %s)
                    ON CONFLICT (station_id) DO UPDATE SET through_time = EXCLUDED.through_time""",
                    (self.settings.station, end))
        return {
            "observations_processed": len(rows),
            "window_start": start.isoformat(), "through_time": end.isoformat(),
            "missing_parameters_in_window": sorted(set(PARAMETERS) - {r[3] for r in rows}),
            "catching_up": end < now,
        }
