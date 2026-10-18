"""Four-state visual comparison for predefined segments, plus portable exports.

Segments shown (rule fixed before plotting): segment 32 (predefined diagnostic), the 'typical' fold (median paired
change rf_xysat - rf_xy under the primary rule, hard scheme), and the 'failure' fold (largest worsening).
For each: real imagery, hidden segment + training bins, coordinate-only RF map, satellite-enhanced RF map, ground truth reveal.
Maps use 100 m cells; a cell is drawn only if (a) its 5x5 20 m window has >= 13 valid water pixels in the scene used for
that segment and (b) it lies within 3 km of a training bin (Phase 1 support rule). Both models are drawn on the same cells.

Exports (exports/): satellite_covariates.tif, predicted_chl_rfu.tif, prediction_support_mask.tif,
segment32_predictions.geojson  - written with --export.
"""
import importlib.util
import json
import sys

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from scipy.spatial import cKDTree

from p2_common import DATA, EXP, FIG, MODEL_VERSION, OUT, xc

_spec = importlib.util.spec_from_file_location("mm", __file__.replace("06_reveal.py", "03_masks_matchup.py"))
mm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mm)
_spec = importlib.util.spec_from_file_location("ex", __file__.replace("06_reveal.py", "04_experiment.py"))
ex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ex)

RULE = "glint_main"
CELL = 100.0
SUPPORT_M = 3000.0
SAT4 = ex.SAT4


def scene_grid(iid, bounds):
    """Satellite features on 100 m cell centres inside bounds, using the same window/mask rule as the bin matchup."""
    S, tf, t = mm.load_scene(iid)
    mask, _ = mm.water_mask(S, **mm.VARIANTS["glint"])
    x0, y0, x1, y1 = bounds
    xs = np.arange(x0 + CELL / 2, x1, CELL)
    ys = np.arange(y1 - CELL / 2, y0, -CELL)
    X, Y = np.meshgrid(xs, ys)
    f, nv = mm.sample(S, mask, tf, X.ravel(), Y.ravel(), glint=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["NDCI"] = (f["B05"] - f["B04"]) / (f["B05"] + f["B04"])
        f["RG"] = f["B04"] / f["B03"]
    return X, Y, f, S, tf, t, mask


def fit_models(M, tr):
    xy = M[["x", "y"]].values
    t = xc.fwd(M.chl_RFU.values, ex.TARGET)
    sat = M[[f"{b}_{RULE}" for b in SAT4]].values
    C = xc.coord_features(xy)
    rf_xy = ex.rf(C[tr], t[tr])
    rf_s = ex.rf(np.column_stack([C, sat])[tr], t[tr])
    mu, sd = sat[tr].mean(0), sat[tr].std(0) + 1e-12
    lin = ex.LinearRegression().fit((sat[tr] - mu) / sd, t[tr])
    gpr = xc.fit_gp(xy[tr], t[tr] - lin.predict((sat[tr] - mu) / sd), n_max=800, seed=0)
    return rf_xy, rf_s, (lin, mu, sd, gpr)


def predict_grid(rf_xy, rf_s, rk, X, Y, f):
    xy = np.column_stack([X.ravel(), Y.ravel()])
    sat = np.column_stack([f[b] for b in SAT4])
    ok = np.isfinite(sat).all(1)
    C = xc.coord_features(xy)
    a = np.full(len(xy), np.nan)
    b = np.full(len(xy), np.nan)
    a[ok] = xc.inv(rf_xy.predict(C[ok]), ex.TARGET)
    b[ok] = xc.inv(rf_s.predict(np.column_stack([C, sat])[ok]), ex.TARGET)
    lin, mu, sd, gpr = rk
    c = np.full(len(xy), np.nan)
    c[ok] = xc.inv(lin.predict((sat[ok] - mu) / sd) + gpr.predict(xy[ok])[0], ex.TARGET)
    return a.reshape(X.shape), b.reshape(X.shape), c.reshape(X.shape), ok.reshape(X.shape)


def figure(M, P, b, label, path):
    blocks = xc.make_blocks(M, 5.0)
    matched = M[f"matched_{RULE}"].values
    te_full, tr_full = xc.fold_split(M, blocks, b, ex.ALONG_BUFFER_M, ex.SPATIAL_BUFFER_M)
    te, tr = te_full[matched[te_full]], tr_full[matched[tr_full]]
    iid = M[f"scene_{RULE}"].iloc[te].mode().iloc[0]
    lag = M[f"lag_h_{RULE}"].iloc[te]
    cx, cy = M.x.values[te_full].mean(), M.y.values[te_full].mean()
    half = 9000.0
    bounds = (cx - half, cy - half, cx + half, cy + half)
    X, Y, f, S, tf, t, mask = scene_grid(iid, bounds)
    rf_xy, rf_s, rk = fit_models(M, tr)
    A, B, Cg, ok = predict_grid(rf_xy, rf_s, rk, X, Y, f)
    d, _ = cKDTree(M[["x", "y"]].values[tr]).query(np.column_stack([X.ravel(), Y.ravel()]))
    sup = (d <= SUPPORT_M).reshape(X.shape)
    A[~sup], B[~sup], Cg[~sup] = np.nan, np.nan, np.nan
    ext = (bounds[0] / 1e3, bounds[2] / 1e3, bounds[1] / 1e3, bounds[3] / 1e3)
    Pf = P[(P.scheme == "hard") & (P.block == b)].sort_values("idx")
    vmax = float(np.nanpercentile(np.r_[M.chl_RFU.values[te_full], M.chl_RFU.values[tr]], 99))
    vmin = 0.3
    norm = matplotlib.colors.LogNorm(vmin, vmax)
    cm = "viridis"

    fig, axs = plt.subplots(2, 4, figsize=(25, 12.5))
    # 1 imagery
    with rasterio.open(DATA / f"{iid}_tci.tif") as src:
        win = rasterio.windows.from_bounds(*bounds, transform=src.transform)
        tci = np.moveaxis(src.read(window=win, boundless=True), 0, -1)
    axs[0, 0].imshow(np.clip(tci * 2.0, 0, 255).astype(np.uint8), extent=ext)
    axs[0, 0].plot(M.x.values[te_full] / 1e3, M.y.values[te_full] / 1e3, "r-", lw=1)
    axs[0, 0].set_title(f"1. Real imagery: {iid[:3]} {t:%Y-%m-%d %H:%M} UTC (true colour x2)\n"
                        f"red = hidden segment; image - boat time {lag.min():+.1f}..{lag.max():+.1f} h", fontsize=9)
    with np.errstate(invalid="ignore", divide="ignore"):
        g4, g5 = S["B04"] - S["B11"], S["B05"] - S["B11"]
        ndci = np.where(mask, (g5 - g4) / (g5 + g4), np.nan)
    r0, r1 = int((tf.f - bounds[3]) / 20), int((tf.f - bounds[1]) / 20)
    c0, c1 = int((bounds[0] - tf.c) / 20), int((bounds[2] - tf.c) / 20)
    im = axs[0, 1].imshow(ndci[r0:r1, c0:c1], extent=ext, cmap="RdYlGn", vmin=-0.3, vmax=0.3)
    axs[0, 1].plot(M.x.values[te_full] / 1e3, M.y.values[te_full] / 1e3, "k-", lw=1)
    axs[0, 1].set_title("2. Satellite input: NDCI from glint-corrected B04/B05 (20 m)\n"
                        "grey = cloud/shadow/shore/glint mask. A spectral index, NOT fluorescence", fontsize=9)
    fig.colorbar(im, ax=axs[0, 1], fraction=0.04, label="NDCI")
    # 3 observed
    sc = axs[0, 2].scatter(M.x.values[tr] / 1e3, M.y.values[tr] / 1e3, c=M.chl_RFU.values[tr], s=6, cmap=cm, norm=norm)
    axs[0, 2].plot(M.x.values[te_full] / 1e3, M.y.values[te_full] / 1e3, "-", color="0.6", lw=4, alpha=0.6)
    axs[0, 2].set_title(f"3. Observed (training bins, hard scheme) - hidden segment {b} in grey\n"
                        f"{len(tr)} training bins; nothing within 1.5 km of the segment", fontsize=9)
    fig.colorbar(sc, ax=axs[0, 2], fraction=0.04, label="chl fluorescence (RFU)")
    im = axs[0, 3].imshow(np.where(mask, S["B05"] - S["B11"], np.nan)[r0:r1, c0:c1], extent=ext, cmap="magma",
                          vmin=0, vmax=0.03)
    axs[0, 3].plot(M.x.values[te_full] / 1e3, M.y.values[te_full] / 1e3, "c-", lw=1)
    axs[0, 3].set_title("Satellite input: B05 red-edge (glint-corrected BOA)\n"
                        "strongest single predictor; tracks turbid plume brightness", fontsize=9)
    fig.colorbar(im, ax=axs[0, 3], fraction=0.04, label="reflectance")
    for a, Z, ttl in [(axs[1, 0], A, "4. Coordinate-only RF (location only)"),
                      (axs[1, 1], B, "5a. Coordinates + satellite RF (B03, B04, B05, NDCI)"),
                      (axs[1, 2], Cg, "5b. GP on coordinates + linear satellite trend")]:
        im = a.imshow(Z, extent=ext, cmap=cm, norm=norm, interpolation="nearest")
        a.scatter(M.x.values[te_full] / 1e3, M.y.values[te_full] / 1e3, s=4, facecolors="none", edgecolors="r", lw=0.4)
        a.set_title(ttl + "\n100 m cells; blank = no valid pixels or > 3 km from evidence", fontsize=9)
        fig.colorbar(im, ax=a, fraction=0.04, label="predicted RFU")
    for a in [axs[0, 0], axs[0, 1], axs[0, 2], axs[0, 3], axs[1, 0], axs[1, 1], axs[1, 2]]:
        a.set_xlim(ext[0], ext[1]); a.set_ylim(ext[2], ext[3]); a.set_facecolor("0.85")
        a.set_xlabel("UTM 16N x (km)"); a.set_aspect("equal")
    # 6 reveal profile
    a = axs[1, 3]
    along = (M.along_m.values[Pf.idx] - M.along_m.values[Pf.idx].min()) / 1e3
    a.plot(along, Pf.y, "k-", lw=2.5, label="TRUTH (revealed)")
    styles = {"idw": ("IDW", "tab:gray", "--"), "rf_xy": ("RF location only", "tab:blue", "-"),
              "gp_xy": ("GP location only", "tab:cyan", "-"), "rf_xysat": ("RF + satellite", "tab:red", "-"),
              "gp_resid": ("GP + satellite trend", "tab:orange", "-")}
    for k, (n, c, ls) in styles.items():
        a.plot(along, Pf[k], ls, color=c, lw=1.4, label=f"{n}: MAE {np.abs(Pf[k] - Pf.y).mean():.2f}")
    a.set_xlabel("distance along hidden segment (km, matched bins only)")
    a.set_ylabel("chl fluorescence (RFU)")
    a.set_title(f"6. Ground-truth reveal, segment {b} ({len(Pf)} of {len(te_full)} bins satellite-matched)", fontsize=9)
    a.legend(fontsize=8)
    fig.suptitle(f"X-Ray the Bay phase 2 - {label}: segment {b}, hard spatial holdout, rule '{RULE}'. "
                 "Target = EXO2 in-vivo chlorophyll fluorescence (RFU), not chlorophyll-a concentration.", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=95)
    plt.close(fig)
    return {"segment": int(b), "label": label, "scene": iid, "lag_h": [float(lag.min()), float(lag.max())],
            "n_test_matched": int(len(te)), "n_test_full": int(len(te_full)), "n_train": int(len(tr)),
            **{f"MAE_{k}": float(np.abs(Pf[k] - Pf.y).mean()) for k in styles}}


def export(M, P):
    """Full-survey model trained on ALL matched bins; 2025-07-01 scene features; 100 m grid over the survey AOI."""
    matched = M[f"matched_{RULE}"].values
    tr = np.where(matched)[0]
    iid = "S2C_T16TDQ_20250701T165332_L2A"
    x0, y0 = np.floor(M.x.min() / 1e3) * 1e3 - 3000, np.floor(M.y.min() / 1e3) * 1e3 - 3000
    x1, y1 = np.ceil(M.x.max() / 1e3) * 1e3 + 3000, np.ceil(M.y.max() / 1e3) * 1e3 + 3000
    X, Y, f, S, tf, t, mask = scene_grid(iid, (x0, y0, x1, y1))
    rf_xy, rf_s, rk = fit_models(M, tr)
    A, B, _, ok = predict_grid(rf_xy, rf_s, rk, X, Y, f)
    d, _ = cKDTree(M[["x", "y"]].values[tr]).query(np.column_stack([X.ravel(), Y.ravel()]))
    sup = ((d <= SUPPORT_M).reshape(X.shape) & ok)
    B[~sup] = np.nan
    H, W = X.shape
    transform = from_origin(x0, y1, CELL, CELL)
    common = dict(driver="GTiff", width=W, height=H, crs="EPSG:32616", transform=transform, compress="deflate")
    tags = dict(model_version=MODEL_VERSION, stac_item=iid, acquisition_utc=str(t), collection="sentinel-2-c1-l2a",
                survey="USGS FLAMe GreenBay_2025_Jun, 2025-06-30 14:25 to 2025-07-01 18:36 UTC, doi:10.5066/P1XHRFKZ",
                crs="EPSG:32616", resolution_m=str(CELL))
    with rasterio.open(EXP / "satellite_covariates.tif", "w", **common, count=4, dtype="float32", nodata=np.nan) as dst:
        for i, k in enumerate(SAT4, 1):
            dst.write(f[k].reshape(X.shape).astype(np.float32), i)
            dst.set_band_description(i, f"{k} glint-corrected BOA reflectance" if k != "NDCI" else "NDCI (unitless)")
        dst.update_tags(**tags, note="median of valid 20 m water pixels per 100 m cell; rho' = rho - rho(B11)")
    with rasterio.open(EXP / "predicted_chl_rfu.tif", "w", **common, count=1, dtype="float32", nodata=np.nan) as dst:
        dst.write(B.astype(np.float32), 1)
        dst.set_band_description(1, "predicted EXO2 chlorophyll fluorescence (RFU), RF coordinates + satellite")
        dst.update_tags(**tags, units="RFU", variable="chl_RFU_exo_tau (in-vivo fluorescence; NOT chlorophyll-a ug/L)",
                        model="RandomForest(300, leaf 3, max_features 0.5) on 9 coordinate + 4 satellite features, "
                              f"trained on {len(tr)} matched 100 m bins (all folds)",
                        validation="see phase2_satellite/RESULTS.md; hard-holdout metrics, not this full fit",
                        support=f"NaN where no valid water pixels or > {SUPPORT_M:.0f} m from a training bin")
    with rasterio.open(EXP / "prediction_support_mask.tif", "w", **common, count=1, dtype="uint8", nodata=255) as dst:
        dst.write(sup.astype(np.uint8), 1)
        dst.update_tags(**tags, meaning="1 = estimate provided; 0 = masked (cloud/shore/glint or > 3 km from evidence)")
    P32 = P[(P.scheme == "hard") & (P.block == 32)]
    g = gpd.GeoDataFrame(P32[["idx", "y", "idw", "rf_xy", "gp_xy", "rf_xysat", "gp_resid"]].rename(columns={"y": "obs_rfu"}),
                         geometry=gpd.points_from_xy(P32.x, P32.y_m), crs=32616).to_crs(4326)
    g["t_utc"] = M.t_utc.values[P32.idx].astype(str)
    g["scene"] = M[f"scene_{RULE}"].values[P32.idx]
    g["lag_h"] = M[f"lag_h_{RULE}"].values[P32.idx]
    g["units"] = "RFU"
    g["scheme"] = "hard holdout (segment 32 hidden + 1 km along-track + 1.5 km spatial buffer)"
    g["model_version"] = MODEL_VERSION
    g.to_file(EXP / "segment32_predictions.geojson", driver="GeoJSON")
    print("exports written", int(sup.sum()), "cells with estimates")


def main():
    M = pd.read_parquet(OUT / "matched_bins.parquet")
    P = pd.read_parquet(OUT / "cv" / f"{RULE}_predictions.parquet")
    F = pd.read_csv(OUT / "cv" / f"{RULE}_folds.csv")
    F = F[(F.scheme == "hard") & F.eligible].copy()
    F["diff"] = F.MAE_rf_xysat - F.MAE_rf_xy
    typical = int(F.iloc[(F["diff"] - F["diff"].median()).abs().argsort().iloc[0]].block)
    failure = int(F.loc[F["diff"].idxmax()].block)
    best = int(F.loc[F["diff"].idxmin()].block)
    info = []
    for b, label in [(32, "predefined diagnostic"), (typical, "typical fold (median change)"),
                     (failure, "failure case (largest worsening)"), (best, "largest improvement")]:
        if b not in set(F.block):
            print("segment", b, "not eligible")
            continue
        info.append(figure(M, P, b, label, FIG / f"reveal_seg{b}.png"))
        if b == 32:
            (FIG / "segment32_satellite_reveal.png").write_bytes((FIG / "reveal_seg32.png").read_bytes())
    (OUT / "reveal_segments.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))
    if "--export" in sys.argv:
        export(M, P)


if __name__ == "__main__":
    main()
