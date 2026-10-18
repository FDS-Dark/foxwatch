"""Fetch recent Sentinel-2 scenes and publish an atomic prediction-map snapshot.

Run with research/xray_bay/.venv/bin/python. --watch checks hourly. The API
only serves completed exports and does not need GDAL or the research environment.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import gzip
import os
from pathlib import Path
import time
import uuid

import numpy as np
import pandas as pd
from PIL import Image
import rasterio
from rasterio.warp import reproject, Resampling, transform_bounds
import requests
from scipy.spatial import cKDTree

import export_xray_bay_map as overview
import export_xray_holdout_maps as hold
from xray_satellite_layer import render_prediction, render_signal
from xray_bay_boundary import clip_export, grid_mask
from xray_live_publish import LiveArtifactPublisher, PublishConfig

AOI = (-88.15, 44.45, -86.65, 45.95)
CACHE = Path(os.getenv("XRAY_LIVE_CACHE_DIR", str(hold.ROOT / ".cache/xray-live")))
OUTPUT = Path(os.getenv("XRAY_LIVE_OUTPUT_DIR", str(hold.ROOT / "data/xray/live")))
CATALOG = "https://earth-search.aws.element84.com/v1"
TILES = ("16TDQ", "16TDR", "16TER")


def utcnow():
    return datetime.now(timezone.utc)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def status(publisher, phase, message, **extra):
    print(message, flush=True)
    payload = {"phase": phase, "message": message, "checked_at": utcnow().isoformat(), **extra}
    atomic_json(OUTPUT / "status.json", payload)
    if publisher is not None:
        publisher.publish_status(payload)


def discover(now, days):
    payload = {"collections": ["sentinel-2-c1-l2a"], "bbox": AOI,
               "datetime": f"{(now - timedelta(days=days)).isoformat()}/{now.isoformat()}",
               "sortby": [{"field": "properties.datetime", "direction": "desc"}], "limit": 100}
    response = requests.post(f"{CATALOG}/search", json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    items = data["features"]
    # Follow pagination so busy acquisition windows do not silently omit tiles.
    for _ in range(10):
        link = next((link for link in data.get("links", []) if link["rel"] == "next"), None)
        if not link:
            break
        response = requests.request(link.get("method", "GET"), link["href"],
                                    json=link.get("body"), timeout=60)
        response.raise_for_status()
        data = response.json()
        items.extend(data["features"])
    selected = []
    for tile in TILES:
        candidates = sorted((i for i in items if f"_T{tile}_" in i["id"]),
                            key=lambda i: i["properties"]["datetime"], reverse=True)
        # Newest acquisitions first, through the first largely clear scene.
        # Bound downloads per tile; retain exact acquisition provenance per cell.
        for item in candidates[:4]:
            selected.append(item)
            if item["properties"].get("eo:cloud_cover", 100) < 10:
                break
    if not selected:
        raise RuntimeError(f"No Sentinel-2 scenes available within {days} days")
    return selected


def download(item):
    downloader = hold.module("live_fetch", "02_fetch_scenes.py")
    downloader.DATA = CACHE / "data"
    downloader.OUT = CACHE
    downloader.ENV.update(GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="2")
    downloader.DATA.mkdir(parents=True, exist_ok=True)
    bbox = item["bbox"]
    downloader.AOI = (max(AOI[0], bbox[0]), max(AOI[1], bbox[1]), min(AOI[2], bbox[2]), min(AOI[3], bbox[3]))
    raster = downloader.DATA / f"{item['id']}_20m.tif"
    color = downloader.DATA / f"{item['id']}_tci.tif"
    if raster.exists() and not color.exists():
        raster.unlink()  # Incomplete download from an interrupted prior run.
    downloader.main([item["id"]])
    return item["id"]


def refresh(days=14, publisher=None):
    now = utcnow()
    status(publisher, "searching", "Checking recent Sentinel-2 acquisitions")
    items = discover(now, days)
    ids = [item["id"] for item in items]
    previous_path = OUTPUT / "manifest.json"
    if publisher is not None:
        previous = publisher.load_previous_manifest(previous_path)
    else:
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
    samples_ok = previous and (
        (OUTPUT / previous["run_id"] / "samples.json.gz").is_file()
        or publisher is not None
    )
    if previous and previous.get("candidate_scene_ids") == ids and samples_ok:
        status(publisher, "ready", "Catalog checked; published map uses the latest selected acquisitions",
               run_id=previous["run_id"], catalog_checked_at=now.isoformat())
        return
    for item in items:
        atomic_json(CACHE / "stac_items" / f"{item['id']}.json", item)
    atomic_json(CACHE / "manifest.json", {"aoi": AOI, "items": ids})
    status(publisher, "downloading", f"Downloading {len(items)} recent scene windows", scene_count=len(items))
    with ProcessPoolExecutor(max_workers=2) as pool:
        for iid in pool.map(download, items):
            print("Ready:", iid, flush=True)
    status(publisher, "predicting", "Masking clouds and applying the research model to recent reflectance")
    X, grid, features, transform, cell, scenes, rgb, scene_index = overview.mosaic_features(CACHE, newest_first=True)
    inside = grid_mask(grid)
    features[~inside] = np.nan
    scene_index[~inside] = 0
    valid = np.isfinite(features).all(1)
    if not valid.any():
        raise RuntimeError("Recent scenes have no usable water pixels after quality masking")
    bins = pd.read_parquet(hold.RESEARCH / "outputs/matched_bins.parquet")
    tr = np.flatnonzero(bins.matched_glint_main.to_numpy())
    xy = bins[["x", "y"]].to_numpy()
    satellite = bins[[f"{band}_glint_main" for band in hold.ex.SAT4]].to_numpy()
    target = hold.xc.fwd(bins.chl_RFU.to_numpy(), hold.ex.TARGET)
    train = np.column_stack([hold.xc.coord_features(xy), satellite])[tr]
    fitted = hold.ex.rf(train, target[tr], seed=0)
    inputs = np.column_stack([hold.xc.coord_features(grid[valid]), features[valid]])
    predictions = np.full(len(grid), np.nan)
    predictions[valid] = hold.xc.inv(fitted.predict(inputs), hold.ex.TARGET)
    distance, _ = cKDTree(xy[tr]).query(grid)
    # Feature-range diagnostics are warnings, not uncertainty estimates.
    outside_features = np.zeros(len(grid), dtype=bool)
    outside_features[valid] = ((features[valid] < satellite[tr].min(0)) |
                               (features[valid] > satellite[tr].max(0))).any(1)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    dest = OUTPUT / run_id
    dest.mkdir(parents=True)
    hold.DEST = dest
    prediction_display = render_prediction(predictions, X.shape, transform, dest)
    bounds = prediction_display["bounds"]
    with Image.open(dest / "prediction.png") as image:
        w, h = image.size
    mercator_bounds = transform_bounds("EPSG:4326", "EPSG:3857", bounds[0][1], bounds[0][0], bounds[1][1], bounds[1][0])
    output_transform = rasterio.transform.from_bounds(*mercator_bounds, w, h)

    def warp(values, resampling=Resampling.nearest):
        output = np.zeros((h, w), dtype="float32")
        reproject(values.reshape(X.shape).astype("float32"), output, src_transform=transform,
                  src_crs="EPSG:32616", dst_transform=output_transform, dst_crs="EPSG:3857", resampling=resampling)
        return output

    support = warp(valid & ((distance > 3000) | outside_features)) > 0
    rows, cols = np.indices(support.shape)
    rgba = np.full((h, w, 4), 255, dtype="uint8")
    rgba[:, :, 3] = np.where(support & ((rows + cols) % 20 < 3), 125, 0)
    Image.fromarray(rgba).save(dest / "support.png")
    satellite_signal = render_signal(features, X.shape, transform, dest)
    ages = np.full(len(grid), np.nan)
    age_reference = utcnow()
    for index, scene in enumerate(scenes, 1):
        scene["index"] = index
        scene["modeled_cells"] = int((scene_index == index).sum())
        acquired = datetime.fromisoformat(scene["acquired_at"].replace("Z", "+00:00"))
        ages[scene_index == index] = (age_reference - acquired).total_seconds() / 86400
    hold.render(ages, X.shape, transform, "age.png", display_max=days, target_crs="EPSG:3857")
    contributing = [s for s in scenes if s["modeled_cells"] > 0]
    dates = sorted(s["acquired_at"] for s in contributing)
    base = {"bounds": bounds, "scope": "recent_satellite_inference", "units": "RFU",
            **prediction_display, "acquired_at": dates[-1], "scene_id": "Recent Sentinel-2 mosaic"}
    def layer_url(key):
        if publisher is not None:
            return publisher.public_layer_url(run_id, key)
        return f"/api/xray/live/{run_id}/{key}"

    layers = [{**base, "id": key, "title": title, "url": layer_url(key),
               **(satellite_signal if key == "satellite" else {}),
               **({"units": "days", "display_min": 0, "display_max": days} if key == "age" else {})}
              for key, title in [("prediction", "Predicted chlorophyll fluorescence"), ("satellite", "Satellite imagery"),
                                 ("support", "Outside training support"), ("age", "Satellite acquisition age")]]
    summary = np.percentile(predictions[valid], [10, 50, 90])
    manifest = {"run_id": run_id, "generated_at": utcnow().isoformat(), "catalog_checked_at": now.isoformat(),
                "candidate_scene_ids": ids, "source": "Copernicus Sentinel-2 / Element 84 Earth Search",
                "acquisition_start": dates[0], "acquisition_end": dates[-1], "max_scene_age_days": days,
                "layers": layers, "scenes": contributing, "resolution_m": cell, "valid_cells": int(valid.sum()),
                "modeled_area_km2": round(valid.sum() * cell * cell / 1e6, 1), "training_bins": len(tr),
                "extrapolated_cells": int((valid & (distance > 3000)).sum()),
                "outside_feature_range_cells": int(outside_features.sum()),
                "statistics": {"p10": float(summary[0]), "median": float(summary[1]), "p90": float(summary[2])},
                "model": "Location + satellite random forest", "training_period": "June 30–July 1, 2025",
                "note": "Experimental transfer of the 2025 FLAMe model to recent satellite imagery; not validated for this season. "
                "Each cell uses the newest valid pixel from the selected acquisitions. Cloud and quality gaps remain transparent. "
                "RFU is predicted fluorescence, not a harmful-bloom probability. USGS station readings are separate live context, not inputs to this map."}
    # Small nearest-cell grid for interactive inspection; no raster libraries in API.
    sample_w, sample_h = w // 4, h // 4
    sample_transform = rasterio.transform.from_bounds(*mercator_bounds, sample_w, sample_h)
    def sample_grid(values, nodata):
        output = np.full((sample_h, sample_w), nodata, dtype="float32")
        reproject(values.reshape(X.shape).astype("float32"), output, src_transform=transform,
                  src_crs="EPSG:32616", dst_transform=sample_transform, dst_crs="EPSG:3857",
                  src_nodata=nodata, dst_nodata=nodata, resampling=Resampling.nearest)
        return output.ravel()
    values = sample_grid(predictions, np.nan)
    sample = {"width": sample_w, "height": sample_h, "bounds": bounds, "projection": "EPSG:3857",
              "values": [round(float(v), 3) if np.isfinite(v) else None for v in values],
              "scenes": sample_grid(scene_index, 0).astype(int).tolist(),
              "outside_support": sample_grid(valid & ((distance > 3000) | outside_features), 0).astype(int).tolist()}
    with gzip.open(dest / "samples.json.gz", "wt") as stream:
        json.dump(sample, stream, separators=(",", ":"), allow_nan=False)
    # Retain the numerical inputs/provenance locally; publish only after all images exist.
    np.savez_compressed(CACHE / f"{run_id}.npz", xy=grid, features=features, prediction=predictions,
                        scene_index=scene_index, training_distance_m=distance, outside_feature_range=outside_features)
    clip_export(dest, manifest)
    atomic_json(dest / "manifest.json", manifest)
    atomic_json(OUTPUT / "manifest.json", manifest)
    if publisher is not None:
        publisher.publish_snapshot(run_id, dest, manifest)
    status(publisher, "ready", f"Published {int(valid.sum()):,} predicted water cells",
           run_id=run_id, catalog_checked_at=now.isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--interval", type=int, default=3600)
    args = parser.parse_args()
    if not 1 <= args.days <= 30 or args.interval < 300:
        parser.error("Use 1–30 days and an interval of at least 300 seconds")
    CACHE.mkdir(parents=True, exist_ok=True)
    # OS-level advisory lock releases on process exit, including interruption.
    lock = (CACHE / "refresh.lock").open("a+")
    if __import__("os").name == "nt":
        import msvcrt
        lock.seek(0); lock.write("0"); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    publish_config = PublishConfig.from_env()
    publisher = LiveArtifactPublisher(publish_config) if publish_config else None
    while True:
        try:
            refresh(args.days, publisher=publisher)
        except Exception as exc:
            status(publisher, "error", f"Refresh failed ({type(exc).__name__}); retaining the last completed map")
            if not args.watch:
                raise
            import traceback
            traceback.print_exc()
        if not args.watch:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
