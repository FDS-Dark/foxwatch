"""Serve completed satellite-inference snapshots independently of research tools."""
from datetime import datetime, timezone
import json
import gzip
from math import log, pi, tan
from functools import lru_cache

from services.xray import XRAY_DIR

LIVE_DIR = XRAY_DIR / "live"


@lru_cache(maxsize=2)
def _sample_grid(run_id):
    with gzip.open(LIVE_DIR / run_id / "samples.json.gz", "rt") as stream:
        return json.load(stream)


def sample_point(run_id, lat, lon):
    grid = _sample_grid(run_id)
    (south, west), (north, east) = grid["bounds"]
    if not south < lat <= north or not west <= lon < east:
        return {"status": "outside", "lat": lat, "lon": lon}
    col = int((lon - west) / (east - west) * grid["width"])
    # Images use Leaflet's Web Mercator, so latitude is nonlinear in pixel rows.
    def mercator_y(latitude):
        return log(tan(pi / 4 + latitude * pi / 360))
    row = int((mercator_y(north) - mercator_y(lat)) /
              (mercator_y(north) - mercator_y(south)) * grid["height"])
    index = row * grid["width"] + col
    value = grid["values"][index]
    if value is None:
        return {"status": "masked", "lat": lat, "lon": lon}
    manifest = json.loads((LIVE_DIR / run_id / "manifest.json").read_text())
    scene = next(s for s in manifest["scenes"] if s["index"] == grid["scenes"][index])
    return {"status": "available", "lat": lat, "lon": lon, "value": value, "units": "RFU",
            "acquired_at": scene["acquired_at"], "scene_id": scene["id"],
            "outside_support": bool(grid["outside_support"][index])}


def live_metadata():
    now = datetime.now(timezone.utc)
    state_path = LIVE_DIR / "status.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {
        "phase": "unavailable", "message": "Waiting for the satellite refresh worker", "checked_at": None,
    }
    checked = state.get("checked_at")
    state["overdue"] = checked is None or (now - datetime.fromisoformat(checked)).total_seconds() > 7200
    manifest_path = LIVE_DIR / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "unavailable", "server_time": now.isoformat(), "refresh": state, "map": None}
    manifest = json.loads(manifest_path.read_text())
    oldest = datetime.fromisoformat(manifest["acquisition_start"].replace("Z", "+00:00"))
    newest = datetime.fromisoformat(manifest["acquisition_end"].replace("Z", "+00:00"))
    return {"status": "stale" if (now - newest).total_seconds() > 3 * 86400 else "ready",
            "server_time": now.isoformat(), "refresh": state, "map": manifest,
            "newest_image_age_hours": round((now - newest).total_seconds() / 3600, 1),
            "oldest_image_age_hours": round((now - oldest).total_seconds() / 3600, 1)}
