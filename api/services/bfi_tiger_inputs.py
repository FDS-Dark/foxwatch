"""Map Tiger / USGS observation rows to BFI calculator inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence


def _reading_value(readings_by_code: Mapping[str, Mapping[str, Any]], code: str) -> Optional[float]:
    row = readings_by_code.get(code)
    if not row:
        return None
    value = row.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def solar_radiation_level_for_month(month: int) -> str:
    if month in (12, 1, 2):
        return "low"
    if month in (3, 4, 9, 10, 11):
        return "moderate"
    return "high"


def bfi_kwargs_from_readings(
    readings: Sequence[Mapping[str, Any]],
    *,
    seasonal_median_streamflow_cfs: Optional[float] = None,
    rainfall_7day_in: Optional[float] = None,
    solar_radiation_level: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> dict[str, Any]:
    by_code = {str(r["parameter_code"]): r for r in readings if r.get("parameter_code")}

    when = as_of or datetime.now(timezone.utc)
    if solar_radiation_level is None:
        solar_radiation_level = solar_radiation_level_for_month(when.month)

    kwargs: dict[str, Any] = {
        "water_temperature_c": _reading_value(by_code, "00010"),
        "orthophosphate_mg_l_as_p": _reading_value(by_code, "00671"),
        "nitrate_nitrite_mg_l_as_n": _reading_value(by_code, "00631"),
        "ammonia_mg_l_as_n": _reading_value(by_code, "00608"),
        "streamflow_cfs": _reading_value(by_code, "00060"),
        "seasonal_median_streamflow_cfs": seasonal_median_streamflow_cfs,
        "rainfall_7day_in": rainfall_7day_in,
        "solar_radiation_level": solar_radiation_level,
    }

    provenance: dict[str, Any] = {
        "source": "tiger_data",
        "as_of": when.isoformat(),
        "station_readings": [],
    }
    labels = {
        "00010": "water_temperature_c",
        "00671": "orthophosphate_mg_l_as_p",
        "00631": "nitrate_nitrite_mg_l_as_n",
        "00608": "ammonia_mg_l_as_n",
        "00060": "streamflow_cfs",
    }
    for code, field in labels.items():
        row = by_code.get(code)
        if not row:
            continue
        provenance["station_readings"].append(
            {
                "bfi_field": field,
                "parameter_code": code,
                "value": row.get("value"),
                "unit": row.get("unit"),
                "observed_at": row.get("observed_at") or row.get("latest_observed_at"),
                "used_fallback": row.get("used_fallback"),
            }
        )
    if seasonal_median_streamflow_cfs is not None:
        provenance["seasonal_median_streamflow_cfs"] = seasonal_median_streamflow_cfs
    if rainfall_7day_in is not None:
        provenance["rainfall_7day_in"] = rainfall_7day_in
    provenance["solar_radiation_level"] = solar_radiation_level
    provenance["solar_radiation_note"] = (
        "Seasonal proxy (no irradiance in USGS ingest); override via API body if needed."
    )

    kwargs["_provenance"] = provenance
    return kwargs
