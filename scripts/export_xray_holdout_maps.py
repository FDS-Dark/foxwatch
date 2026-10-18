"""Render the existing holdout models as geographic layers, without new models.

Uses the research model definitions, folds, masks and seeds. Reproduces saved
point predictions before exporting any map. Run with the research environment.
"""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from PIL import Image
import rasterio
from rasterio.transform import from_origin, array_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling
from scipy.spatial import cKDTree
from matplotlib import colormaps

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research/xray_bay/phase2_satellite"
DEST = ROOT / "data/xray/holdouts"
sys.path.insert(0, str(RESEARCH / "scripts"))


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, RESEARCH / "scripts" / filename)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


ex = module("experiment", "04_experiment.py")
mm = module("matchup", "03_masks_matchup.py")
xc = ex.xc


def render(values, shape, transform, filename, display_max=16):
    height, width = shape
    bounds = array_bounds(height, width, transform)
    dst_transform, w, h = calculate_default_transform("EPSG:32616", "EPSG:4326", width, height, *bounds)
    # Interpolate the display between prediction cells without filling masked
    # areas or changing the saved predictions used for evaluation.
    dst_transform = dst_transform * rasterio.Affine.scale(0.25, 0.25)
    w, h = w * 4, h * 4
    warped = np.full((h, w), np.nan, dtype="float32")
    reproject(values.reshape(shape), warped, src_transform=transform, src_crs="EPSG:32616",
              dst_transform=dst_transform, dst_crs="EPSG:4326", src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.bilinear)
    colors = colormaps["viridis"](np.clip(np.nan_to_num(warped / display_max), 0, 1), bytes=True)
    colors[~np.isfinite(warped), 3] = 0
    Image.fromarray(colors).save(DEST / filename)
    west, south, east, north = array_bounds(h, w, dst_transform)
    return [[south, west], [north, east]]


def main(bay=False):
    DEST.mkdir(parents=True, exist_ok=True)
    bins = pd.read_parquet(RESEARCH / "outputs/matched_bins.parquet")
    saved = pd.read_parquet(RESEARCH / "outputs/cv/glint_main_predictions.parquet")
    blocks = xc.make_blocks(bins, 5.0)
    matched = bins.matched_glint_main.to_numpy()
    xy = bins[["x", "y"]].to_numpy()
    target = xc.fwd(bins.chl_RFU.to_numpy(), ex.TARGET)
    coords = xc.coord_features(xy)
    satellite = bins[[f"{b}_glint_main" for b in ex.SAT4]].to_numpy()
    exports = {}
    for segment in (32, 31, 17):
        print(f"Rendering segment {segment}: same hard-holdout seed and training bins", flush=True)
        te_full, tr_full = xc.fold_split(bins, blocks, segment, 1000, 1500)
        te, tr = te_full[matched[te_full]], tr_full[matched[tr_full]]
        reference = saved[(saved.scheme == "hard") & (saved.block == segment)].sort_values("idx")
        if not np.array_equal(te, reference.idx):
            raise ValueError("Fold indices differ")
        rf_location = ex.rf(coords[tr], target[tr], seed=segment)
        rf_satellite = ex.rf(np.column_stack([coords, satellite])[tr], target[tr], seed=segment)
        mu, sd = satellite[tr].mean(0), satellite[tr].std(0) + 1e-12
        trend = ex.LinearRegression().fit((satellite[tr] - mu) / sd, target[tr])
        gp = xc.fit_gp(xy[tr], target[tr] - trend.predict((satellite[tr] - mu) / sd), n_max=800, seed=segment)
        check = {
            "rf_xy": xc.inv(rf_location.predict(coords[te]), ex.TARGET),
            "rf_xysat": xc.inv(rf_satellite.predict(np.column_stack([coords, satellite])[te]), ex.TARGET),
            "gp_resid": xc.inv(trend.predict((satellite[te] - mu) / sd) + gp.predict(xy[te])[0], ex.TARGET),
        }
        for model, values in check.items():
            delta = float(np.max(np.abs(values - reference[model].to_numpy())))
            if not np.allclose(values, reference[model], atol=0.001, rtol=0.001):
                raise ValueError(f"{model} predictions differ from saved holdout by {delta}")
            print(f"  {model}: saved-prediction max difference {delta:.8f} RFU", flush=True)
        if bay:
            mosaic = np.load(RESEARCH / "bay_overview" / "overview_inputs.npz")
            grid, grid_sat = mosaic["xy"], mosaic["satellite"]
            width, height = len(np.unique(grid[:, 0])), len(np.unique(grid[:, 1]))
            transform = from_origin(grid[:, 0].min() - 100, grid[:, 1].max() + 100, 200, 200)
            scene, acquired_at = "Expanded multi-date mosaic", "2025-06-30 / 2025-07-01 / 2025-07-03"
            distance, _ = cKDTree(xy[tr]).query(grid)
            valid = np.isfinite(grid_sat).all(1)
        else:
            # As in the original research visual, use the dominant matched scene
            # for the continuous map. Individual evaluation points retain their
            # own matched scene; their errors are never calculated from this raster.
            scene = bins.scene_glint_main.iloc[te].mode().iloc[0]
            minimum, maximum = xy[te_full].min(0) - 4000, xy[te_full].max(0) + 4000
            west, south = np.floor(minimum / 100) * 100
            east, north = np.ceil(maximum / 100) * 100
            width, height = int((east - west) / 100), int((north - south) / 100)
            transform = from_origin(west, north, 100, 100)
            X, Y = np.meshgrid(np.arange(west + 50, east, 100), np.arange(north - 50, south, -100))
            grid = np.column_stack([X.ravel(), Y.ravel()])
            with rasterio.open(RESEARCH / "data" / f"{scene}_20m.tif") as src:
                window = rasterio.windows.from_bounds(west - 400, south - 400, east + 400, north + 400, src.transform).round_offsets().round_lengths()
                image = src.read(window=window, boundless=True, fill_value=np.nan)
                bands = {name: image[i] for i, name in enumerate(src.descriptions)}
                scene_transform = src.window_transform(window)
                acquired_at = src.tags()["datetime_utc"]
            mask, _ = mm.water_mask(bands, **mm.VARIANTS["glint"])
            features, _ = mm.sample(bands, mask, scene_transform, grid[:, 0], grid[:, 1], glint=True)
            with np.errstate(invalid="ignore", divide="ignore"):
                features["NDCI"] = (features["B05"] - features["B04"]) / (features["B05"] + features["B04"])
            grid_sat = np.column_stack([features[b] for b in ex.SAT4])
            distance, _ = cKDTree(xy[tr]).query(grid)
            valid = np.isfinite(grid_sat).all(1) & (distance <= 3000)
        grid_coords = xc.coord_features(grid[valid])
        # Bound GP memory when rendering the whole bay.
        valid_grid = grid[valid]
        gp_residual = np.concatenate([gp.predict(valid_grid[start:start + 2000])[0]
                                      for start in range(0, len(valid_grid), 2000)])
        outputs = {
            "rf_xy": xc.inv(rf_location.predict(grid_coords), ex.TARGET),
            "rf_xysat": xc.inv(rf_satellite.predict(np.column_stack([grid_coords, grid_sat[valid]])), ex.TARGET),
            "gp_resid": xc.inv(trend.predict((grid_sat[valid] - mu) / sd) + gp_residual, ex.TARGET),
        }
        layers = {}
        for model, predictions in outputs.items():
            values = np.full(len(grid), np.nan)
            values[valid] = predictions
            name = f"{segment}_{model}{'_bay' if bay else ''}.png"
            bounds = render(values, (height, width), transform, name)
            layers[model] = {"url": f"/api/xray/holdouts/{segment}/{model}" + ("?extent=bay" if bay else ""), "bounds": bounds,
                             "title": model, "units": "RFU", "scene_id": scene, "acquired_at": acquired_at,
                             "display_min": 0, "display_max": 16, "scope": "holdout_extrapolation" if bay else "hard_holdout", "id": model}
        exports[str(segment)] = {"layers": layers, "training_bins": len(tr), "matched_test_bins": len(te),
                                 "resolution_m": 200 if bay else 100, "support_radius_m": 3000,
                                 "note": ("Whole-bay fields use the expanded multi-date mosaic and include extrapolation beyond 3 km from training evidence. Scored points retain their original satellite matches; the broader field is not additional validation." if bay else "Maps use the dominant scene for continuous context. Scored points use their individual matched scenes. Blank = invalid water pixels or >3 km from training evidence.")}
        if bay:
            with Image.open(DEST / f"{segment}_rf_xy_bay.png") as image:
                w, h = image.size
            tf = rasterio.transform.from_bounds(bounds[0][1], bounds[0][0], bounds[1][1], bounds[1][0], w, h)
            unsupported = np.zeros((h, w), dtype="uint8")
            reproject((valid & (distance > 3000)).reshape(height, width).astype("uint8"), unsupported,
                      src_transform=transform, src_crs="EPSG:32616", dst_transform=tf, dst_crs="EPSG:4326", resampling=Resampling.nearest)
            rows, cols = np.indices((h, w))
            hatch = np.full((h, w, 4), 255, dtype="uint8")
            hatch[:, :, 3] = np.where((unsupported > 0) & ((rows + cols) % 20 < 3), 130, 0)
            Image.fromarray(hatch).save(DEST / f"{segment}_extrapolation_bay.png")
            exports[str(segment)]["extrapolation"] = {**layers["rf_xy"], "id": "extrapolation", "title": "Beyond training support",
                                                        "url": f"/api/xray/holdouts/{segment}/extrapolation?extent=bay"}
    destination = DEST / ("manifest_bay.json" if bay else "manifest.json")
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(exports, indent=2) + "\n")
    temporary.replace(destination)
    print("Holdout maps exported; no hidden targets were used in fitting.", flush=True)


if __name__ == "__main__":
    main(bay="--bay" in sys.argv)
