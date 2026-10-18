"""Non-Tiger BFI inputs: Open-Meteo rainfall and WQP discrete nutrient samples."""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx

from models.bfi_factors import mm_to_inches

LOGGER = logging.getLogger(__name__)

WQP_RESULT_SEARCH = "https://www.waterqualitydata.us/data/Result/search"
USGS_MONITORING_LOCATION = (
    "https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/items"
)
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"

# USGS parameter codes we map from WQP narrowResult rows.
_WQP_NUTRIENT_CODES = ("00671", "00631", "00608", "00665")

_wqp_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_WQP_CACHE_SECONDS = 3600.0


@dataclass(frozen=True)
class StationCoordinates:
    latitude: float
    longitude: float


def monitoring_location_coordinates(
    station_id: str,
    *,
    client: httpx.Client | None = None,
) -> Optional[StationCoordinates]:
    """Resolve lat/lon from USGS OGC monitoring-locations (GeoJSON Point)."""
    own = client is None
    if own:
        client = httpx.Client(timeout=20)
    try:
        response = client.get(f"{USGS_MONITORING_LOCATION}/{station_id}", params={"f": "json"})
        response.raise_for_status()
        geometry = response.json().get("geometry") or {}
        coords = geometry.get("coordinates")
        if not coords or len(coords) < 2:
            return None
        lon, lat = float(coords[0]), float(coords[1])
        return StationCoordinates(latitude=lat, longitude=lon)
    except Exception as exc:
        LOGGER.warning("Failed to load coordinates for %s: %s", station_id, exc)
        return None
    finally:
        if own:
            client.close()


def rainfall_7day_in_open_meteo(
    latitude: float,
    longitude: float,
    *,
    client: httpx.Client | None = None,
) -> Optional[float]:
    """
    Sum daily precipitation over the last 7 completed local days (Open-Meteo, mm → in).
    """
    own = client is None
    if own:
        client = httpx.Client(timeout=25)
    try:
        response = client.get(
            OPEN_METEO_FORECAST,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "precipitation_sum",
                "past_days": 7,
                "forecast_days": 0,
                "timezone": "America/Chicago",
            },
        )
        response.raise_for_status()
        daily = response.json().get("daily") or {}
        amounts_mm = daily.get("precipitation_sum") or []
        if not amounts_mm:
            return None
        total_mm = sum(float(x) for x in amounts_mm if x is not None)
        return mm_to_inches(total_mm)
    except Exception as exc:
        LOGGER.warning("Open-Meteo rainfall fetch failed: %s", exc)
        return None
    finally:
        if own:
            client.close()


def _parse_wqp_nutrient_rows(csv_text: str) -> dict[str, Any]:
    """Pick the most recent numeric result per USGS parameter code."""
    latest: dict[str, tuple[str, float, str]] = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        code = (row.get("USGSPCode") or "").strip()
        if code not in _WQP_NUTRIENT_CODES:
            continue
        value_raw = (row.get("ResultMeasureValue") or "").strip()
        if not value_raw:
            continue
        try:
            value = float(value_raw)
        except ValueError:
            continue
        sample_date = (row.get("ActivityStartDate") or "").strip()
        unit = (row.get("ResultMeasure/MeasureUnitCode") or "").strip()
        prev = latest.get(code)
        if prev is None or sample_date > prev[0]:
            latest[code] = (sample_date, value, unit)

    out: dict[str, Any] = {
        "source": "water_quality_portal",
        "wqp_url": WQP_RESULT_SEARCH,
        "samples": [],
        "note": (
            "Discrete lab samples from Water Quality Portal; not USGS continuous telemetry. "
            "Dates may lag real-time conditions."
        ),
    }
    field_map = {
        "00671": "orthophosphate_mg_l_as_p",
        "00631": "nitrate_nitrite_mg_l_as_n",
        "00608": "ammonia_mg_l_as_n",
        "00665": "total_phosphorus_mg_l_as_p",
    }
    kwargs: dict[str, Any] = {}
    for code, field in field_map.items():
        if code not in latest:
            continue
        sample_date, value, unit = latest[code]
        kwargs[field] = value
        out["samples"].append(
            {
                "bfi_field": field,
                "usgs_parameter_code": code,
                "value": value,
                "unit": unit,
                "sample_date": sample_date,
            }
        )
    if kwargs:
        out["latest_sample_date"] = max(s["sample_date"] for s in out["samples"])
    out.update(kwargs)
    return out


def wqp_latest_nutrients(
    station_id: str,
    *,
    client: httpx.Client | None = None,
    max_rows: int = 5000,
) -> dict[str, Any]:
    """
    Latest phosphorus / nitrogen related samples for a USGS monitoring location.

    WQP returns CSV; we filter rows with USGSPCode 00671, 00631, 00608, 00665.
    """
    now = time.monotonic()
    cached = _wqp_cache.get(station_id)
    if cached and now - cached[0] < _WQP_CACHE_SECONDS:
        return dict(cached[1])

    own = client is None
    if own:
        client = httpx.Client(timeout=120)
    try:
        response = client.get(
            WQP_RESULT_SEARCH,
            params={
                "countrycode": "US",
                "siteid": station_id,
                "mimeType": "csv",
                "zip": "no",
                "dataProfile": "narrowResult",
                "maxrows": str(max_rows),
            },
        )
        response.raise_for_status()
        payload = _parse_wqp_nutrient_rows(response.text)
        _wqp_cache[station_id] = (now, payload)
        return dict(payload)
    except Exception as exc:
        LOGGER.warning("WQP nutrient fetch failed for %s: %s", station_id, exc)
        return {"source": "water_quality_portal", "error": str(exc), "samples": []}
    finally:
        if own:
            client.close()


def enrich_live_bfi_kwargs(
    calc: dict[str, Any],
    provenance: dict[str, Any] | None,
    *,
    station_id: str,
    client: httpx.Client | None = None,
) -> None:
    """
    Fill missing rainfall and nutrient BFI fields from Open-Meteo and WQP.

    Mutates ``calc`` and ``provenance`` in place.
    """
    if provenance is None:
        provenance = {}
    supplemental = provenance.setdefault("supplemental", [])

    own = client is None
    if own:
        client = httpx.Client(timeout=120)

    try:
        if calc.get("rainfall_7day_in") is None:
            coords = monitoring_location_coordinates(station_id, client=client)
            if coords:
                rain = rainfall_7day_in_open_meteo(
                    coords.latitude, coords.longitude, client=client
                )
                if rain is not None:
                    calc["rainfall_7day_in"] = rain
                    entry = {
                        "bfi_field": "rainfall_7day_in",
                        "source": "open_meteo",
                        "value_in": rain,
                        "latitude": coords.latitude,
                        "longitude": coords.longitude,
                        "window_days": 7,
                    }
                    supplemental.append(entry)
                    provenance["rainfall_7day_in"] = rain
                    provenance["rainfall_source"] = "open_meteo"

        needs_p = calc.get("orthophosphate_mg_l_as_p") is None and calc.get("phosphorus_ug_l") is None
        needs_n = (
            calc.get("nitrate_nitrite_mg_l_as_n") is None
            and calc.get("ammonia_mg_l_as_n") is None
            and calc.get("nitrogen_mg_l") is None
        )
        if needs_p or needs_n:
            wqp = wqp_latest_nutrients(station_id, client=client)
            if wqp.get("samples"):
                supplemental.append({"source": "water_quality_portal", **wqp})
                for field in (
                    "orthophosphate_mg_l_as_p",
                    "nitrate_nitrite_mg_l_as_n",
                    "ammonia_mg_l_as_n",
                    "total_phosphorus_mg_l_as_p",
                ):
                    if calc.get(field) is None and wqp.get(field) is not None:
                        calc[field] = wqp[field]
                provenance["nutrient_samples_source"] = "water_quality_portal"
                if wqp.get("latest_sample_date"):
                    provenance["nutrient_latest_sample_date"] = wqp["latest_sample_date"]
                provenance["nutrient_samples_note"] = wqp.get("note")
    finally:
        if own:
            client.close()
