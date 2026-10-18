"""Serve completed satellite-inference snapshots independently of research tools."""
from datetime import datetime, timezone
import gzip
import json
from math import log, pi, tan
from functools import lru_cache
from urllib.parse import urljoin

import httpx

import settings
from services.xray import XRAY_DIR

LIVE_DIR = XRAY_DIR / "live"
_FETCH_TIMEOUT = 30.0
_NO_STORE = {"Cache-Control": "no-store"}


def _live_prefix(base: str) -> str:
    return urljoin(base.rstrip("/") + "/", "live/")


def _remote_enabled() -> bool:
    return bool(settings.XRAY_LIVE_PUBLIC_BASE_URL)


def _fetch_bytes(url: str) -> bytes:
    with httpx.Client(timeout=_FETCH_TIMEOUT) as client:
        response = client.get(url, headers=_NO_STORE)
        response.raise_for_status()
        return response.content


def _fetch_json(url: str) -> dict:
    return json.loads(_fetch_bytes(url).decode("utf-8"))


def _read_local_json(path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_refresh_status() -> dict:
    if _remote_enabled():
        try:
            return _fetch_json(_live_prefix(settings.XRAY_LIVE_PUBLIC_BASE_URL) + "status.json")
        except (httpx.HTTPError, json.JSONDecodeError, OSError):
            pass
    return _read_local_json(LIVE_DIR / "status.json") or {
        "phase": "unavailable",
        "message": "Waiting for the satellite refresh worker",
        "checked_at": None,
    }


def load_root_manifest() -> dict | None:
    if _remote_enabled():
        try:
            return _fetch_json(_live_prefix(settings.XRAY_LIVE_PUBLIC_BASE_URL) + "manifest.json")
        except (httpx.HTTPError, json.JSONDecodeError, OSError):
            pass
    return _read_local_json(LIVE_DIR / "manifest.json")


def load_run_manifest(run_id: str) -> dict:
    if _remote_enabled():
        url = _live_prefix(settings.XRAY_LIVE_PUBLIC_BASE_URL) + f"{run_id}/manifest.json"
        return _fetch_json(url)
    path = LIVE_DIR / run_id / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _sample_grid(run_id: str):
    if _remote_enabled():
        url = _live_prefix(settings.XRAY_LIVE_PUBLIC_BASE_URL) + f"{run_id}/samples.json.gz"
        payload = gzip.decompress(_fetch_bytes(url))
        return json.loads(payload.decode("utf-8"))
    with gzip.open(LIVE_DIR / run_id / "samples.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


def sample_point(run_id, lat, lon):
    grid = _sample_grid(run_id)
    (south, west), (north, east) = grid["bounds"]
    if not south < lat <= north or not west <= lon < east:
        return {"status": "outside", "lat": lat, "lon": lon}
    col = int((lon - west) / (east - west) * grid["width"])

    def mercator_y(latitude):
        return log(tan(pi / 4 + latitude * pi / 360))

    row = int(
        (mercator_y(north) - mercator_y(lat))
        / (mercator_y(north) - mercator_y(south))
        * grid["height"]
    )
    index = row * grid["width"] + col
    value = grid["values"][index]
    if value is None:
        return {"status": "masked", "lat": lat, "lon": lon}
    manifest = load_run_manifest(run_id)
    scene = next(s for s in manifest["scenes"] if s["index"] == grid["scenes"][index])
    return {
        "status": "available",
        "lat": lat,
        "lon": lon,
        "value": value,
        "units": "RFU",
        "acquired_at": scene["acquired_at"],
        "scene_id": scene["id"],
        "outside_support": bool(grid["outside_support"][index]),
    }


def live_metadata():
    now = datetime.now(timezone.utc)
    state = load_refresh_status()
    checked = state.get("checked_at")
    if checked is None:
        state["overdue"] = True
    else:
        checked_at = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        state["overdue"] = (now - checked_at).total_seconds() > 7200
    manifest = load_root_manifest()
    if manifest is None:
        return {"status": "unavailable", "server_time": now.isoformat(), "refresh": state, "map": None}
    oldest = datetime.fromisoformat(manifest["acquisition_start"].replace("Z", "+00:00"))
    newest = datetime.fromisoformat(manifest["acquisition_end"].replace("Z", "+00:00"))
    return {
        "status": "stale" if (now - newest).total_seconds() > 3 * 86400 else "ready",
        "server_time": now.isoformat(),
        "refresh": state,
        "map": manifest,
        "newest_image_age_hours": round((now - newest).total_seconds() / 3600, 1),
        "oldest_image_age_hours": round((now - oldest).total_seconds() / 3600, 1),
    }
