"""Background USGS collector: polls Water Data API and upserts into Postgres/Timescale."""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

import httpx
import psycopg

from models.usgs import REQUESTED_PARAMETER_CODES
from services.usgs_client import fetch_features, observation_row, utcnow
from settings import IngestionSettings

LOGGER = logging.getLogger(__name__)

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


class UsgsCollector:
    def __init__(self, settings: IngestionSettings):
        self.settings = settings
        self.lock = threading.Lock()
        self.status = {
            "configured": bool(settings.database_url),
            "enabled": settings.enabled,
            "station_id": settings.station,
            "requested_parameters": list(REQUESTED_PARAMETER_CODES),
            "poll_seconds": settings.poll_seconds,
            "running": False,
            "last_success": None,
            "last_error": None,
        }

    def client(self) -> httpx.Client:
        headers = {"X-Api-Key": self.settings.api_key} if self.settings.api_key else {}
        return httpx.Client(headers=headers, timeout=30)

    def latest_usgs_preview(self) -> dict:
        with self.client() as client:
            features = list(fetch_features(client, "latest-continuous", self.settings.station))
        readings = [
            f["properties"]
            for f in features
            if observation_row(f, self.settings.station) is not None
        ]
        available = {p["parameter_code"] for p in readings}
        return {
            "station_id": self.settings.station,
            "readings": readings,
            "missing_parameters": sorted(set(REQUESTED_PARAMETER_CODES) - available),
        }

    def poll(self) -> dict:
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
            self.status["last_error"] = type(exc).__name__
            LOGGER.error("USGS ingestion failed (%s); retrying on the next poll", type(exc).__name__)
            raise
        finally:
            self.status["running"] = False
            self.lock.release()

    def _poll(self) -> dict:
        rows: list = []
        with psycopg.connect(
            self.settings.database_url,
            connect_timeout=10,
            options="-c statement_timeout=30000",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(748392061)")
                if not cursor.fetchone()[0]:
                    return {"skipped": "Another worker is ingesting"}
                for statement in SCHEMA:
                    cursor.execute(statement)
                cursor.execute(
                    "SELECT through_time FROM usgs_ingestion_checkpoints WHERE station_id = %s",
                    (self.settings.station,),
                )
                checkpoint = cursor.fetchone()
                now = utcnow()
                through = checkpoint[0] if checkpoint else now - timedelta(hours=24)
                start = through - timedelta(hours=self.settings.overlap_hours) if checkpoint else through
                end = min(now, through + timedelta(days=1))
                with self.client() as client:
                    rows = [
                        row
                        for feature in fetch_features(
                            client, "continuous", self.settings.station, start, end
                        )
                        if (row := observation_row(feature, self.settings.station)) is not None
                    ]
                if rows:
                    cursor.executemany(UPSERT, rows)
                cursor.execute(
                    """INSERT INTO usgs_ingestion_checkpoints VALUES (%s, %s)
                    ON CONFLICT (station_id) DO UPDATE SET through_time = EXCLUDED.through_time""",
                    (self.settings.station, end),
                )
        return {
            "observations_processed": len(rows),
            "window_start": start.isoformat(),
            "through_time": end.isoformat(),
            "missing_parameters_in_window": sorted(set(REQUESTED_PARAMETER_CODES) - {r[3] for r in rows}),
            "catching_up": end < now,
        }


class UsgsIngestionService:
    def __init__(self, collector: UsgsCollector):
        self.collector = collector

    def status(self) -> dict:
        return self.collector.status.copy()

    def poll(self) -> dict:
        return self.collector.poll()

    def latest_usgs(self) -> dict:
        return self.collector.latest_usgs_preview()


# Test compatibility aliases
Collector = UsgsCollector
Settings = IngestionSettings
