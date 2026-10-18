"""Render live prediction and water-only satellite layers with full color ranges.

Running this file republishes the current snapshot from cached numerical inputs;
no downloads, model fitting, API changes, or process restarts are required.
"""
from datetime import datetime, timezone
import json
import shutil
import uuid

import numpy as np
from rasterio.transform import from_origin

import export_xray_holdout_maps as hold
from xray_bay_boundary import clip_export, grid_mask, rebuild_samples


def render_prediction(values, shape, transform, dest):
    finite = values[np.isfinite(values)]
    low = min(0.0, float(np.floor(finite.min() / 4) * 4))
    high = max(low + 4, float(np.ceil(finite.max() / 4) * 4))
    hold.DEST = dest
    bounds = hold.render(values, shape, transform, "prediction.png", display_min=low,
                         display_max=high, target_crs="EPSG:3857")
    return {"bounds": bounds, "display_min": low, "display_max": high,
            "description": "Color range covers all finite predictions in this snapshot; numerical predictions are unchanged."}


def render_signal(features, shape, transform, dest):
    # B03 is an actual model input, after the same SWIR glint correction.
    # Retain the original water/cloud mask; never color the RGB cloud background.
    valid = np.isfinite(features).all(1)
    values = np.where(valid, features[:, hold.ex.SAT4.index("B03")], np.nan)
    low = float(np.floor(values[valid].min() * 100) / 100)
    high = float(np.ceil(values[valid].max() * 100) / 100)
    if high <= low:
        high = low + 0.01
    hold.DEST = dest
    bounds = hold.render(values, shape, transform, "satellite.png", display_min=float(low),
                         display_max=float(high), target_crs="EPSG:3857")
    return {"title": "Green-band reflectance", "units": "reflectance", "scope": "satellite_signal",
            "bounds": bounds, "display_min": float(low), "display_max": float(high),
            "description": "Sentinel-2 B03 reflectance after SWIR glint correction. Water-only color display; "
            "the color range covers all finite values in this snapshot. This is a satellite input, not a fluorescence prediction."}


def republish():
    live = hold.ROOT / "data/xray/live"
    pointer = live / "manifest.json"
    metadata = json.loads(pointer.read_text())
    previous_id = metadata["run_id"]
    numerical_id = metadata.get("numerical_run_id", previous_id)
    cache = np.load(hold.ROOT / ".cache/xray-live" / f"{numerical_id}.npz")
    grid = cache["xy"]
    inside = grid_mask(grid)
    predictions = np.where(inside, cache["prediction"], np.nan)
    features = np.where(inside[:, None], cache["features"], np.nan)
    valid = np.isfinite(predictions)
    cell = metadata["resolution_m"]
    shape = (len(np.unique(grid[:, 1])), len(np.unique(grid[:, 0])))
    transform = from_origin(grid[:, 0].min() - cell / 2, grid[:, 1].max() + cell / 2, cell, cell)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    dest = live / run_id
    dest.mkdir()
    for name in ("age.png", "support.png", "samples.json.gz"):
        shutil.copy2(live / previous_id / name, dest / name)
    prediction = render_prediction(predictions, shape, transform, dest)
    signal = render_signal(features, shape, transform, dest)
    rebuild_samples(dest, predictions, cache["scene_index"],
                    (cache["training_distance_m"] > 3000) | cache["outside_feature_range"], shape, transform)
    metadata.update(run_id=run_id, numerical_run_id=numerical_id, visualization_updated_at=now.isoformat())
    metadata["valid_cells"] = int(valid.sum())
    metadata["modeled_area_km2"] = round(valid.sum() * cell * cell / 1e6, 1)
    metadata["extrapolated_cells"] = int((valid & (cache["training_distance_m"] > 3000)).sum())
    metadata["outside_feature_range_cells"] = int((valid & cache["outside_feature_range"]).sum())
    metadata["statistics"] = dict(zip(("p10", "median", "p90"), np.percentile(predictions[valid], [10, 50, 90]).tolist()))
    for scene in metadata["scenes"]:
        scene["modeled_cells"] = int((valid & (cache["scene_index"] == scene["index"])).sum())
    metadata["scenes"] = [scene for scene in metadata["scenes"] if scene["modeled_cells"]]
    dates = sorted(scene["acquired_at"] for scene in metadata["scenes"])
    metadata.update(acquisition_start=dates[0], acquisition_end=dates[-1])
    for layer in metadata["layers"]:
        if layer["id"] == "prediction":
            layer.update(prediction)
        if layer["id"] == "satellite":
            layer.update(signal)
        layer["url"] = f"/api/xray/live/{run_id}/{layer['id']}"
    clip_export(dest, metadata)
    payload = json.dumps(metadata, indent=2, allow_nan=False) + "\n"
    (dest / "manifest.json").write_text(payload)
    # Do not overwrite a newer acquisition if the hourly worker published meanwhile.
    if json.loads(pointer.read_text())["run_id"] != previous_id:
        raise RuntimeError("A newer map was published; rerun against that snapshot")
    temporary = live / f"manifest.{uuid.uuid4().hex}.tmp"
    temporary.write_text(payload)
    temporary.replace(pointer)
    print(f"Published expanded color scales: {run_id}")
    print(f"Prediction color scale: {prediction['display_min']:g} to {prediction['display_max']:g} RFU")
    print(f"Reflectance color scale: {signal['display_min']:.4f} to {signal['display_max']:.4f}")
    print(f"Green Bay cells retained: {int(valid.sum()):,}; outside-bay cells removed: {int((~inside & np.isfinite(cache['prediction'])).sum()):,}")


if __name__ == "__main__":
    republish()
