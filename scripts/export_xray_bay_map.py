"""Render existing full-survey RF models over the available satellite footprint.

Unlike holdout exports, this view includes extrapolation beyond 3 km from
training evidence. It is visualization, not additional validation.
"""
import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from PIL import Image
from pyproj import Transformer
from scipy.spatial import cKDTree

import export_xray_holdout_maps as hold


def mosaic_features():
    source = hold.RESEARCH / "bay_overview"
    manifest = json.loads((source / "manifest.json").read_text())
    west, south, east, north = manifest["aoi"]
    project = Transformer.from_crs(4326, 32616, always_xy=True)
    xs, ys = project.transform([west, east, west, east], [south, south, north, north])
    cell = 200
    west, south = np.floor(np.array([min(xs), min(ys)]) / cell) * cell
    east, north = np.ceil(np.array([max(xs), max(ys)]) / cell) * cell
    X, Y = np.meshgrid(np.arange(west + cell / 2, east, cell), np.arange(north - cell / 2, south, -cell))
    grid = np.column_stack([X.ravel(), Y.ravel()])
    transform = from_origin(west, north, cell, cell)
    grid_sat = np.full((len(grid), len(hold.ex.SAT4)), np.nan)
    rgb = np.zeros((3, *X.shape), dtype="uint8")
    scene_index = np.zeros(len(grid), dtype="uint8")
    scenes = []
    # Prefer July 1, then June 30; July 3 fills remaining quality/coverage gaps.
    ids = sorted(manifest["items"], key=lambda iid: ("20250701" not in iid, iid))
    for index, iid in enumerate(ids, 1):
        print("Sampling", iid, flush=True)
        with rasterio.open(source / "data" / f"{iid}_20m.tif") as src:
            data = src.read()
            bands = {name: data[i] for i, name in enumerate(src.descriptions)}
            mask, _ = hold.mm.water_mask(bands, **hold.mm.VARIANTS["glint"])
            f, _ = hold.mm.sample(bands, mask, src.transform, grid[:, 0], grid[:, 1], glint=True)
            acquired_at = src.tags()["datetime_utc"]
        with np.errstate(divide="ignore", invalid="ignore"):
            f["NDCI"] = (f["B05"] - f["B04"]) / (f["B05"] + f["B04"])
        values = np.column_stack([f[b] for b in hold.ex.SAT4])
        use = ~np.isfinite(grid_sat).all(1) & np.isfinite(values).all(1)
        grid_sat[use] = values[use]
        scene_index[use] = index
        with rasterio.open(source / "data" / f"{iid}_tci.tif") as src:
            image = np.zeros_like(rgb)
            for band in range(3):
                reproject(rasterio.band(src, band + 1), image[band], src_transform=src.transform,
                          src_crs=src.crs, dst_transform=transform, dst_crs="EPSG:32616", resampling=Resampling.average)
        # RGB context follows the same selected source at modeled water cells.
        take_image = (rgb.max(0) == 0) | use.reshape(X.shape)
        rgb[:, take_image] = image[:, take_image]
        scenes.append({"id": iid, "acquired_at": acquired_at, "modeled_cells": int(use.sum()),
                       "url": f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a/items/{iid}"})
        del bands, data, mask, image
    return X, grid, grid_sat, transform, cell, scenes, rgb, scene_index


def main():
    dest = hold.ROOT / "data/xray/bay"
    dest.mkdir(parents=True, exist_ok=True)
    hold.DEST = dest
    bins = pd.read_parquet(hold.RESEARCH / "outputs/matched_bins.parquet")
    tr = np.flatnonzero(bins.matched_glint_main.to_numpy())
    xy = bins[["x", "y"]].to_numpy()
    target = hold.xc.fwd(bins.chl_RFU.to_numpy(), hold.ex.TARGET)
    coordinates = hold.xc.coord_features(xy)
    satellite = bins[[f"{band}_glint_main" for band in hold.ex.SAT4]].to_numpy()
    models = {
        "rf_xy": hold.ex.rf(coordinates[tr], target[tr], seed=0),
        "rf_xysat": hold.ex.rf(np.column_stack([coordinates, satellite])[tr], target[tr], seed=0),
    }
    X, grid, grid_sat, transform, cell, scenes, rgb, scene_index = mosaic_features()
    valid = np.isfinite(grid_sat).all(1)
    distances, _ = cKDTree(xy[tr]).query(grid)
    layers = []
    predictions = {}
    for model, fitted in models.items():
        inputs = hold.xc.coord_features(grid[valid])
        if model == "rf_xysat":
            inputs = np.column_stack([inputs, grid_sat[valid]])
        values = np.full(len(grid), np.nan)
        values[valid] = hold.xc.inv(fitted.predict(inputs), hold.ex.TARGET)
        predictions[model] = values
        bounds = hold.render(values, X.shape, transform, f"{model}.png", display_max=4)
        layers.append({"id": model, "title": "Location + satellite RF" if model == "rf_xysat" else "Location-only RF",
                       "url": f"/api/xray/bay/{model}", "bounds": bounds, "units": "RFU", "scope": "full_fit_extrapolation",
                       "display_min": 0, "display_max": 4, "scene_id": "June 30–July 3 mosaic", "acquired_at": "2025-06-30 / 2025-07-01 / 2025-07-03"})
    # Hatch only the valid-water estimates outside the original support radius.
    with Image.open(dest / "rf_xy.png") as image:
        w, h = image.size
    bounds = layers[0]["bounds"]
    output_transform = rasterio.transform.from_bounds(bounds[0][1], bounds[0][0], bounds[1][1], bounds[1][0], w, h)
    outside = np.zeros((h, w), dtype="uint8")
    reproject((valid & (distances > 3000)).reshape(X.shape).astype("uint8"), outside,
              src_transform=transform, src_crs="EPSG:32616", dst_transform=output_transform,
              dst_crs="EPSG:4326", resampling=Resampling.nearest)
    rows, cols = np.indices(outside.shape)
    rgba = np.zeros((h, w, 4), dtype="uint8")
    rgba[:, :, :3] = 255
    rgba[:, :, 3] = np.where((outside > 0) & ((rows + cols) % 20 < 3), 130, 0)
    Image.fromarray(rgba).save(dest / "extrapolation.png")
    color = np.zeros((4, h, w), dtype="uint8")
    for band in range(3):
        reproject(rgb[band], color[band], src_transform=transform, src_crs="EPSG:32616", dst_transform=output_transform,
                  dst_crs="EPSG:4326", resampling=Resampling.bilinear)
    color[:3] = np.clip(color[:3].astype(float) * 1.5, 0, 255).astype("uint8")
    color[3] = np.where(color[:3].max(0) > 0, 255, 0)
    Image.fromarray(np.moveaxis(color, 0, -1)).save(dest / "satellite.png")
    # Retain numerical predictions and per-cell acquisition provenance for inspection.
    np.savez_compressed(hold.RESEARCH / "bay_overview" / "overview_inputs.npz",
                        xy=grid, satellite=grid_sat, scene_index=scene_index, training_distance_m=distances, **predictions)
    manifest = {"layers": layers, "extrapolation": {**layers[0], "id": "extrapolation", "title": "Outside training support",
                 "url": "/api/xray/bay/extrapolation"}, "training_bins": len(tr), "resolution_m": cell,
                "satellite": {**layers[0], "id": "satellite", "title": "Sentinel-2 true color mosaic", "url": "/api/xray/bay/satellite", "units": "RGB", "scope": "satellite_context"},
                "scenes": scenes,
                "valid_cells": int(valid.sum()), "extrapolated_cells": int((valid & (distances > 3000)).sum()),
                "note": "Full-survey fit, not held-out validation. Predictions beyond 3 km of training measurements are extrapolation. "
                "The overview prefers July 1 imagery, uses June 30 at the northeastern edge, and fills remaining gaps from July 3. It is not a simultaneous bay-wide observation. "
                "Uncolored water has cloud, quality-mask, or image-coverage gaps; no satellite-informed prediction is supplied there."}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Exported {valid.sum()} water cells; {manifest['extrapolated_cells']} are extrapolated", flush=True)


if __name__ == "__main__":
    main()
