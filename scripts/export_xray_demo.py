"""Package existing research outputs for the app; never fit a model.

Run with the research environment: research/xray_bay/.venv/bin/python
scripts/export_xray_demo.py. Requires pandas, pyarrow, scipy, rasterio and Pillow.
The API only needs the resulting JSON/PNG files, not these export dependencies.
"""
from pathlib import Path
import hashlib
import json
import shutil

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research/xray_bay"
PHASE2 = RESEARCH / "phase2_satellite"
DEST = ROOT / "data/xray"
MODELS = {
    "rf_xy": "Location-only random forest",
    "gp_xy": "Location-only Gaussian process",
    "idw": "Distance-weighted interpolation",
    "rf_xysat": "Location + satellite random forest (primary)",
    "gp_resid": "Satellite trend + spatial Gaussian process (diagnostic)",
}


def export_layers():
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from PIL import Image
    from matplotlib import colormaps

    layers = []
    for name, filename, band, title, units, scope in [
        ("satellite", "satellite_covariates.tif", 3, "July 1 red-edge reflectance", "reflectance", "satellite_context"),
        ("reconstruction", "predicted_chl_rfu.tif", 1, "Full-survey RF reconstruction", "RFU", "full_fit_not_holdout"),
    ]:
        path = PHASE2 / "exports" / filename
        with rasterio.open(path) as src:
            transform, width, height = calculate_default_transform(src.crs, "EPSG:4326", src.width, src.height, *src.bounds)
            values = np.full((height, width), np.nan, dtype="float32")
            reproject(src.read(band), values, src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs="EPSG:4326", src_nodata=np.nan,
                      dst_nodata=np.nan, resampling=Resampling.nearest)
            valid = np.isfinite(values)
            low, high = np.percentile(values[valid], [2, 98])
            rgba = colormaps["viridis"](np.clip(np.nan_to_num((values - low) / (high - low)), 0, 1), bytes=True)
            rgba[~valid, 3] = 0
            Image.fromarray(rgba).save(DEST / f"{name}.png")
            west, south, east, north = rasterio.transform.array_bounds(height, width, transform)
            layers.append({"id": name, "title": title, "units": units, "scope": scope,
                           "url": f"/api/xray/layers/{name}", "bounds": [[south, west], [north, east]],
                           "display_min": float(low), "display_max": float(high),
                           "acquired_at": src.tags().get("acquisition_utc"),
                           "scene_id": src.tags().get("stac_item"),
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return layers


def export():
    DEST.mkdir(parents=True, exist_ok=True)
    matched_path = PHASE2 / "outputs/matched_bins.parquet"
    prediction_path = PHASE2 / "outputs/cv/glint_main_predictions.parquet"
    obs_path = RESEARCH / "outputs/geo/observations_GreenBay_2025_Jun__chl_RFU_exo_tau.geojson"
    metrics_path = PHASE2 / "outputs/metrics.json"
    bins = pd.read_parquet(matched_path)
    predictions = pd.read_parquet(prediction_path)
    predictions = predictions[predictions.scheme == "hard"]
    geo = json.loads(obs_path.read_text())["features"]
    metrics = json.loads(metrics_path.read_text())["rules"]["glint_main"]["schemes"]["hard"]
    folds = pd.read_csv(PHASE2 / "outputs/cv/glint_main_folds.csv")
    if len(geo) != len(bins):
        raise ValueError("Observation export and matched-bin index differ")
    observations = []
    for idx, row in bins.iterrows():
        prop = geo[idx]["properties"]
        if not np.isclose(prop["value"], row.chl_RFU) or prop["segment"] != row.block:
            raise ValueError(f"Observation alignment failed at {idx}")
        observations.append({
            "id": int(idx), "lat": float(row.lat), "lon": float(row.lon),
            "observed_at": row.t_utc.isoformat().replace("+00:00", "Z"),
            "along_m": float(row.along_m), "segment": int(row.block),
            "value": float(row.chl_RFU), "raw_samples": int(row.n_raw),
        })
    cases = {}
    for segment, label in [(32, "Plume recovery"), (31, "Failure case"), (17, "Typical case")]:
        target = bins.block.to_numpy() == segment
        along = bins.along_m.to_numpy()
        distances = cKDTree(bins.loc[target, ["x", "y"]]).query(bins[["x", "y"]])[0]
        train = (~target & ((along < along[target].min() - 1000) | (along > along[target].max() + 1000))
                 & (distances > 1500) & bins.matched_glint_main.to_numpy())
        heldout = predictions[predictions.block == segment].sort_values("idx")
        fold = folds[(folds.scheme == "hard") & (folds.block == segment)].iloc[0]
        if len(heldout) != fold.n_test or train.sum() != fold.n_train:
            raise ValueError(f"Fold membership differs for segment {segment}")
        points = []
        for _, row in heldout.iterrows():
            obs = observations[int(row.idx)]
            if obs["segment"] != segment or not np.isclose(obs["value"], row.y):
                raise ValueError("Held-out predictions do not align with measurements")
            points.append({"id": obs["id"], "distance_km": (obs["along_m"] - along[target].min()) / 1000,
                           "predictions": {key: float(row[key]) for key in MODELS},
                           "scene_id": bins.iloc[int(row.idx)].scene_glint_main,
                           "lag_hours": float(bins.iloc[int(row.idx)].lag_h_glint_main)})
        errors = {}
        for key in MODELS:
            error = heldout[key] - heldout.y
            mae = float(error.abs().mean())
            if not np.isclose(mae, fold[f"MAE_{key}"]):
                raise ValueError("Recomputed error differs from research report")
            errors[key] = {"mae": mae, "bias": float(error.mean()), "rmse": float(np.sqrt((error**2).mean()))}
        cases[str(segment)] = {
            "id": segment, "label": label, "train_ids": np.flatnonzero(train).tolist(),
            "target_ids": np.flatnonzero(target).tolist(), "points": points, "metrics": errors,
        }
    scenes = []
    for scene_id in sorted({p["scene_id"] for c in cases.values() for p in c["points"]}):
        item = json.loads((PHASE2 / f"outputs/stac_items/{scene_id}.json").read_text())
        scenes.append({"id": scene_id, "acquired_at": item["properties"]["datetime"]})
    sources = [
        {"id": "usgs", "title": "USGS FLAMe data release · Loken et al., 2026", "url": "https://doi.org/10.5066/P1XHRFKZ"},
        {"id": "observations", "title": "Timestamped 100 m FLAMe observation bins", "url": "/api/xray/evidence/observations"},
        {"id": "results", "title": "Phase 2 evaluation and limitations", "url": "/api/xray/evidence/results"},
        {"id": "decision", "title": "Research decision: conditional go", "url": "/api/xray/evidence/decision"},
        {"id": "metrics", "title": "Hard spatial holdout metrics", "url": "/api/xray/evidence/metrics"},
        {"id": "segment32", "title": "Segment 32 held-out predictions (GeoJSON)", "url": "/api/xray/evidence/segment32"},
    ]
    bundle = {
        "campaign": "GreenBay_2025_Jun", "title": "X-Ray the Bay", "units": "RFU",
        "variable": "EXO2 in-vivo chlorophyll fluorescence", "model_version": "xray-bay-p2-0.1.0",
        "aggregation": "Sensor-response-corrected measurements, median aggregated into 100 m along-track bins",
        "protocol": "Saved hard spatial holdout: a 5 km segment, 1 km along-track buffer, and 1.5 km spatial exclusion. Identical matched training/test bins for all models.",
        "start": observations[0]["observed_at"], "end": observations[-1]["observed_at"],
        "observations": observations, "cases": cases, "models": MODELS, "scenes": scenes,
        "overall": {"folds": metrics["n_folds"], "test_bins": metrics["n_test_bins"],
                    "models": {k: metrics["models"][k] for k in MODELS},
                    "primary_comparison": metrics["paired"]["rf_xysat_vs_rf_xy"],
                    "diagnostic_comparison": metrics["paired"]["gp_resid_vs_rf_xy"]},
        "layers": export_layers(),
        "limitations": [
            "RFU is a sensor fluorescence signal, not chlorophyll-a concentration, a toxin measurement, or confirmed harmful blooms.",
            "The satellite signal also tracks turbid plume brightness; it is not specific to chlorophyll.",
            "Segment 32 is a diagnostic example, not proof of general improvement. Segment 31 shows a failure.",
            "The primary random-forest comparison improves pooled MAE by 3.4%; its 95% bootstrap interval includes no improvement.",
            "The diagnostic satellite-trend model is worse than the location-only random forest in 33 of 48 folds.",
            "Satellite acquisitions may precede or follow the boat by up to 24 hours. These are historical reconstructions, not forecasts.",
        ], "sources": sources,
        "provenance": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in (matched_path, prediction_path, obs_path, metrics_path)],
    }
    (DEST / "demo.json").write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False) + "\n")
    evidence = DEST / "evidence"
    evidence.mkdir(exist_ok=True)
    for source, name in [(obs_path, "observations.geojson"), (metrics_path, "metrics.json"),
                         (PHASE2 / "RESULTS.md", "results.md"), (PHASE2 / "DECISION.md", "decision.md"),
                         (PHASE2 / "exports/segment32_predictions.geojson", "segment32.geojson")]:
        shutil.copyfile(source, evidence / name)
    print(f"Packaged {len(observations)} observations and {len(cases)} verified holdout cases into {DEST}")


if __name__ == "__main__":
    export()
