"""USGS Water Data OGC API client helpers (fetch + normalize features)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from psycopg.types.json import Jsonb

from models.usgs import REQUESTED_PARAMETER_CODES

BASE_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fetch_features(client: httpx.Client, collection: str, station: str, start=None, end=None):
    params = {"f": "json", "monitoring_location_id": station, "limit": 1000}
    if start is not None:
        params["datetime"] = f"{start.isoformat()}/{end.isoformat()}"
    url = f"{BASE_URL}/{collection}/items"
    seen: set[str] = set()
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
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.waterdata.usgs.gov" or url in seen:
            raise ValueError("Invalid USGS pagination link")
        seen.add(url)
        params = None
    raise ValueError("USGS pagination exceeded the per-poll limit")


def observation_row(feature: dict, station: str):
    p = feature["properties"]
    if p["monitoring_location_id"] != station or p["parameter_code"] not in REQUESTED_PARAMETER_CODES:
        return None
    observed_at = datetime.fromisoformat(p["time"].replace("Z", "+00:00"))
    if observed_at.tzinfo is None:
        raise ValueError("USGS observation has no timezone")
    try:
        value = float(p["value"])
        if not math.isfinite(value):
            value = None
    except (TypeError, ValueError):
        value = None
    return (
        observed_at,
        p["time_series_id"],
        station,
        p["parameter_code"],
        value,
        p.get("unit_of_measure"),
        p.get("approval_status"),
        Jsonb(p),
    )
