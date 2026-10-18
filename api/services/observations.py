from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from databridge.postgres_databridge import PostgresDatabridge
from models.usgs import REQUESTED_PARAMETER_CODES
from services.usgs_client import utcnow


LATEST_PER_PARAMETER = """
    SELECT DISTINCT ON (parameter_code)
        parameter_code, time_series_id, observed_at, value, unit,
        approval_status, source->>'qualifier' AS qualifier, ingested_at
    FROM usgs_observations
    WHERE station_id = :station_id AND parameter_code = ANY(:codes)
    ORDER BY parameter_code, observed_at DESC, time_series_id ASC
"""

PREDICTION_READINGS = """
    WITH latest AS (
        SELECT DISTINCT ON (parameter_code) *
        FROM usgs_observations
        WHERE station_id = :station_id AND parameter_code = ANY(:codes)
        ORDER BY parameter_code, observed_at DESC, time_series_id ASC
    )
    SELECT latest.parameter_code, latest.observed_at AS latest_observed_at,
        COALESCE(latest.value, previous.value) AS value,
        CASE WHEN latest.value IS NULL THEN previous.observed_at ELSE latest.observed_at END AS observed_at,
        CASE WHEN latest.value IS NULL THEN previous.unit ELSE latest.unit END AS unit,
        CASE WHEN latest.value IS NULL THEN previous.approval_status ELSE latest.approval_status END AS approval_status,
        CASE WHEN latest.value IS NULL THEN previous.time_series_id ELSE latest.time_series_id END AS time_series_id,
        CASE WHEN latest.value IS NULL THEN previous.source->>'qualifier' ELSE latest.source->>'qualifier' END AS qualifier,
        (latest.value IS NULL AND previous.value IS NOT NULL) AS used_fallback
    FROM latest
    LEFT JOIN LATERAL (
        SELECT * FROM usgs_observations AS history
        WHERE latest.value IS NULL AND history.station_id = latest.station_id
            AND history.parameter_code = latest.parameter_code
            AND history.observed_at <= latest.observed_at AND history.value IS NOT NULL
        ORDER BY history.observed_at DESC, history.time_series_id ASC LIMIT 1
    ) AS previous ON TRUE
    ORDER BY latest.parameter_code
"""


def _records(df) -> list[dict[str, Any]]:
    if df.empty:
        return []
    rows = df.to_dict(orient="records")
    for row in rows:
        for key, value in row.items():
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat() if isinstance(value, datetime) else value
    return rows


class ObservationsService:
    def __init__(self, databridge: PostgresDatabridge, station_id: str):
        self.databridge = databridge
        self.station_id = station_id

    async def latest_stored(self) -> dict[str, Any]:
        df = await self.databridge.execute_query(
            LATEST_PER_PARAMETER,
            {"station_id": self.station_id, "codes": list(REQUESTED_PARAMETER_CODES)},
        )
        readings = _records(df)
        available = {row["parameter_code"] for row in readings}
        return {
            "source": "tiger_data",
            "station_id": self.station_id,
            "requested_parameters": list(REQUESTED_PARAMETER_CODES),
            "readings": readings,
            "missing_parameters": sorted(set(REQUESTED_PARAMETER_CODES) - available),
            "fetched_at": utcnow().isoformat(),
            # Hourly USGS publication batches plus transmission and ingestion time.
            "stale_after_seconds": 2 * 60 * 60,
        }

    async def prediction_readings(self, parameter_codes: list[str]) -> list[dict[str, Any]]:
        df = await self.databridge.execute_query(
            PREDICTION_READINGS,
            {"station_id": self.station_id, "codes": list(parameter_codes)},
        )
        return _records(df)
