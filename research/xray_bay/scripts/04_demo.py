"""X-Ray the Bay demonstration: observe -> hide -> reconstruct -> reveal -> suggest, plus portable exports.

Also runs the active-sampling replay (Experiment 7): for every held-out segment, which single point on the hidden
segment, if measured first, most reduces error on the rest of the segment? Compares GP max-variance and integrated
variance reduction (IVR) against random choice.

Outputs
  figures/xray_demo_<cfg>_seg<k>.png        four-state demo figure
  figures/active_sampling_<cfg>.png
  outputs/geo/observations_<cfg>.geojson    thinned survey bins (WGS84)
  outputs/geo/demo_holdout_<cfg>_seg<k>.geojson   hidden bins with truth/prediction/error/interval
  outputs/geo/reconstruction_<cfg>_seg<k>.tif     demo-fold reconstruction (EPSG:32616)
  outputs/geo/reconstruction_<cfg>_full.tif       reconstruction from all bins
  outputs/geo/sampling_candidates_<cfg>.geojson   suggested next measurements
  outputs/demo_summary.json, outputs/active_sampling_<cfg>.json
"""
import json
import sys

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import LogNorm, Normalize, TwoSlopeNorm
from matplotlib.patches import Patch
from rasterio.transform import from_origin
from scipy.linalg import cho_solve
from scipy.spatial import cKDTree
from scipy.stats import norm
from shapely import contains_xy

from xray_common import (EPSG, FIG, LABELS, LOG_TARGETS, MODEL_VERSION, OUT, UNITS, fit_gp, fold_split, fwd, inv,
                         load_observations, make_blocks, metrics, predict_idw, water_polygon)

CAMPAIGN = "GreenBay_2025_Jun"
TARGET = "chl_RFU_exo_tau"
BLOCK_KM, ALONG_BUFFER_M = 5.0, 1000.0  # identical to 03_experiment.py standard scheme
GRID_M = 250.0
SUPPORT_M = 3000.0  # no estimate further than this from the nearest training bin
GEO = OUT / "geo"
PROVENANCE = ("USGS data release doi:10.5066/P1XHRFKZ (Loken et al., 2026), FLAMe_data.csv; "
              "EXO2 tau-corrected sensor values, median-aggregated to 100 m along-track bins")


def grid_for(obs, water):
    x0, x1 = obs.x.min() - 3000, obs.x.max() + 3000
    y0, y1 = obs.y.min() - 3000, obs.y.max() + 3000
    xs = np.arange(x0 + GRID_M / 2, x1, GRID_M)
    ys = np.arange(y1 - GRID_M / 2, y0, -GRID_M)  # north-up rows
    X, Y = np.meshgrid(xs, ys)
    inwater = contains_xy(water, X.ravel(), Y.ravel()).reshape(X.shape)
    return xs, ys, X, Y, inwater


def reconstruct(obs, tr, X, Y, inwater, seed=0):
    xy = obs[["x", "y"]].values
    t = fwd(obs.value.values, TARGET)
    gp = fit_gp(xy[tr], t[tr], n_max=1500, seed=seed)
    G = np.column_stack([X.ravel(), Y.ravel()])
    d, _ = cKDTree(xy[tr]).query(G)
    support = (d <= SUPPORT_M).reshape(X.shape) & inwater
    mu = np.full(G.shape[0], np.nan)
    sd = np.full(G.shape[0], np.nan)
    s = support.ravel()
    mu[s], sd[s] = gp.predict(G[s])
    return gp, mu.reshape(X.shape), sd.reshape(X.shape), support, d.reshape(X.shape)


def write_geotiff(path, xs, ys, bands, names, tags):
    transform = from_origin(xs[0] - GRID_M / 2, ys[0] + GRID_M / 2, GRID_M, GRID_M)
    with rasterio.open(path, "w", driver="GTiff", height=len(ys), width=len(xs), count=len(bands), dtype="float32",
                       crs=f"EPSG:{EPSG}", transform=transform, nodata=np.nan, compress="deflate") as dst:
        for i, (b, n) in enumerate(zip(bands, names), 1):
            dst.write(b.astype("float32"), i)
            dst.set_band_description(i, n)
        dst.update_tags(**tags)


def to_wgs84_points(df, x="x", y="y"):
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[x], df[y]), crs=EPSG).to_crs(4326)


def posterior_cross(gp, A, B):
    """Posterior latent covariance between point sets A and B (standardised model space, km coordinates)."""
    g = gp.gp
    Xtr = g.X_train_
    kA = g.kernel_(A / 1000.0, Xtr)
    kB = g.kernel_(B / 1000.0, Xtr)
    return g.kernel_(A / 1000.0, B / 1000.0) - kA @ cho_solve((g.L_, True), kB.T)


def ivr_scores(gp, cand, evalpts):
    """Integrated variance reduction over evalpts from one noisy observation at each candidate."""
    g = gp.gp
    cov_ec = posterior_cross(gp, evalpts, cand)
    kc = g.kernel_(cand / 1000.0, g.X_train_)
    var_c = g.kernel_.diag(cand / 1000.0) - np.einsum("ij,ji->i", kc, cho_solve((g.L_, True), kc.T))
    return (cov_ec**2).sum(0) / np.maximum(var_c, 1e-12)


def refit_with(gp_fold, obs, tr, extra):
    """Refit with frozen hyperparameters after revealing `extra` bins."""
    xy = obs[["x", "y"]].values
    t = fwd(obs.value.values, TARGET)
    idx = np.concatenate([tr, extra])
    return fit_gp(xy[idx], t[idx], n_max=len(idx), kernel=gp_fold.gp.kernel_)


def active_sampling_replay(obs, blocks, rng_draws=20):
    xy = obs[["x", "y"]].values
    v = obs.value.values
    rows = []
    for b in np.unique(blocks):
        te, tr = fold_split(obs, blocks, b, ALONG_BUFFER_M)
        if len(te) < 15:
            continue
        # frozen-kernel GP on (a subsample of) training data; subsample kept fixed so only the reveal differs
        rng = np.random.default_rng(b)
        tr_s = rng.choice(tr, size=min(800, len(tr)), replace=False)
        gp0 = fit_gp(xy[tr_s], fwd(v[tr_s], TARGET), n_max=len(tr_s), seed=int(b))
        base = metrics(v[te], inv(gp0.predict(xy[te])[0], TARGET))["MAE"]
        _, sd = gp0.predict(xy[te])
        picks = {"max_sd": te[np.argmax(sd)], "ivr": te[np.argmax(ivr_scores(gp0, xy[te], xy[te]))],
                 "max_dist": te[np.argmax(cKDTree(xy[tr_s]).query(xy[te])[0])]}

        def mae_after(p):
            gp1 = refit_with(gp0, obs, tr_s, np.array([p]))
            rest = te[te != p]
            return metrics(v[rest], inv(gp1.predict(xy[rest])[0], TARGET))["MAE"]

        r = {"block": int(b), "n_test": len(te), "mae_before": base}
        for k, p in picks.items():
            r[f"mae_{k}"] = mae_after(p)
        r["mae_random"] = float(np.mean([mae_after(p) for p in rng.choice(te, size=rng_draws, replace=False)]))
        rows.append(r)
    return pd.DataFrame(rows)


def demo_figure(obs, b, te, tr, gp, X, Y, mu, sd, support, water, path, title_extra):
    v = obs.value.values
    xy = obs[["x", "y"]].values
    lo, hi = np.percentile(v, [1, 99])
    cnorm = LogNorm(max(lo, 0.1), hi) if TARGET in LOG_TARGETS else Normalize(lo, hi)
    cmap = "viridis"
    removed = np.setdiff1d(np.arange(len(obs)), np.concatenate([te, tr]))
    mu_v = inv(mu, TARGET)
    pred_te_t, sd_te = gp.predict(xy[te])  # exact points, not grid lookup
    pred_te = inv(pred_te_t, TARGET)
    err = pred_te - v[te]
    z80 = norm.ppf(0.9)
    inside80 = np.abs(fwd(v[te], TARGET) - pred_te_t) <= z80 * sd_te
    m = metrics(v[te], pred_te)
    m_idw = metrics(v[te], predict_idw(xy[tr], v[tr], xy[te]))

    fig, axes = plt.subplots(2, 3, figsize=(19, 15))
    ext = [X.min() - GRID_M / 2, X.max() + GRID_M / 2, Y.min() - GRID_M / 2, Y.max() + GRID_M / 2]
    bx = np.r_[xy[te, 0].min() - 6000, xy[te, 0].max() + 6000]
    by = np.r_[xy[te, 1].min() - 6000, xy[te, 1].max() + 6000]

    def base(ax, title, zoom=False):
        gpd.GeoSeries([water], crs=EPSG).plot(ax=ax, color="#eef3f8", edgecolor="#8aa6c8", lw=0.6)
        ax.set_title(title, fontsize=11, loc="left")
        ax.set_aspect("equal")
        ax.set_xlim(*(bx if zoom else (obs.x.min() - 3000, obs.x.max() + 3000)))
        ax.set_ylim(*(by if zoom else (obs.y.min() - 3000, obs.y.max() + 3000)))
        ax.set_xticks([])
        ax.set_yticks([])

    ax = axes[0, 0]
    base(ax, "A. Observed: research-vessel track (100 m bins)")
    sc = ax.scatter(xy[:, 0], xy[:, 1], c=v, s=5, cmap=cmap, norm=cnorm)
    plt.colorbar(sc, ax=ax, shrink=0.7, label=LABELS[TARGET])

    ax = axes[0, 1]
    base(ax, "B. Hidden: one survey segment withheld")
    ax.scatter(xy[tr, 0], xy[tr, 1], c=v[tr], s=5, cmap=cmap, norm=cnorm)
    ax.scatter(xy[te, 0], xy[te, 1], s=14, facecolor="none", edgecolor="#d62728", lw=0.8, label=f"hidden ({len(te)} bins)")
    ax.scatter(xy[removed, 0], xy[removed, 1], s=5, color="#bbbbbb", label=f"buffer, also removed ({len(removed)})")
    ax.legend(loc="lower right", fontsize=9)

    ax = axes[0, 2]
    base(ax, "C. Reconstruction (GP mean)\ngrey = no estimate (>3 km from evidence / outside water mask)")
    ax.imshow(np.where(support, mu_v, np.nan), extent=ext, cmap=cmap, norm=cnorm, origin="upper", zorder=2, interpolation="nearest")
    ax.imshow(np.where(support, np.nan, 1.0), extent=ext, cmap="Greys", vmin=0, vmax=4, origin="upper", zorder=2, alpha=0.35)
    ax.scatter(xy[tr, 0], xy[tr, 1], s=0.6, color="k", alpha=0.5, zorder=3)
    ax.plot(*np.array(_hull(xy[te])).T, color="#d62728", lw=1.2, ls="--", zorder=4)

    ax = axes[1, 0]
    base(ax, "C'. Uncertainty: GP predictive SD (model space)\nheuristic until checked by held-out coverage")
    im = ax.imshow(np.where(support, sd, np.nan), extent=ext, cmap="magma_r", origin="upper", zorder=2, interpolation="nearest")
    plt.colorbar(im, ax=ax, shrink=0.7, label="SD of log(RFU+1)" if TARGET in LOG_TARGETS else "SD")
    ax.scatter(xy[tr, 0], xy[tr, 1], s=0.6, color="k", alpha=0.5, zorder=3)

    ax = axes[1, 1]
    base(ax, "D. Reveal: hidden measurements vs prediction (zoom)", zoom=True)
    ax.imshow(np.where(support, mu_v, np.nan), extent=ext, cmap=cmap, norm=cnorm, origin="upper", zorder=2, alpha=0.55)
    emax = np.percentile(np.abs(err), 95)
    sc = ax.scatter(xy[te, 0], xy[te, 1], zorder=4, c=err, s=26, cmap="RdBu_r", norm=TwoSlopeNorm(0, -emax, emax),
                    edgecolor=np.where(inside80, "k", "#ff7f0e"), lw=0.6)
    plt.colorbar(sc, ax=ax, shrink=0.7, label=f"prediction - truth ({UNITS[TARGET]})")
    ax.scatter(xy[tr, 0], xy[tr, 1], s=3, c=v[tr], cmap=cmap, norm=cnorm, zorder=3)
    ax.legend(handles=[Patch(edgecolor="k", facecolor="none", label="truth inside 80% interval"),
                       Patch(edgecolor="#ff7f0e", facecolor="none", label="truth outside 80% interval")], fontsize=9)

    ax = axes[1, 2]
    order = np.argsort(obs.along_m.values[te])
    a = (obs.along_m.values[te][order] - obs.along_m.values[te].min()) / 1000
    ax.fill_between(a, inv(pred_te_t - z80 * sd_te, TARGET)[order], inv(pred_te_t + z80 * sd_te, TARGET)[order],
                    color="#1f77b4", alpha=0.2, label="GP 80% interval")
    ax.plot(a, pred_te[order], color="#1f77b4", lw=2, label="GP reconstruction")
    ax.plot(a, predict_idw(xy[tr], v[tr], xy[te])[order], color="#7f7f7f", lw=1.5, ls="--", label="IDW baseline")
    ax.plot(a, v[te][order], color="k", lw=1.5, marker=".", ms=4, label="hidden measurement (truth)")
    ax.set_xlabel("distance along hidden segment (km)")
    ax.set_ylabel(LABELS[TARGET])
    ax.legend(fontsize=9)
    ax.set_title(f"D'. Along the hidden segment ({len(te)} bins)\nGP: MAE {m['MAE']:.2f}, RMSE {m['RMSE']:.2f} {UNITS[TARGET]} | "
                 f"IDW: MAE {m_idw['MAE']:.2f}, RMSE {m_idw['RMSE']:.2f}\nGP 80% interval hit rate {inside80.mean():.0%}",
                 fontsize=10, loc="left")
    fig.suptitle(f"X-Ray the Bay - {CAMPAIGN} ({obs.t_utc.min():%Y-%m-%d} to {obs.t_utc.max():%Y-%m-%d})\n"
                 f"{LABELS[TARGET]} - hidden segment {b} {title_extra}", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return m, m_idw, float(inside80.mean()), pred_te, pred_te_t, sd_te


def _hull(pts):
    from shapely import MultiPoint
    h = MultiPoint(pts).convex_hull.buffer(400)
    return list(h.exterior.coords)


def main():
    global CAMPAIGN, TARGET
    if len(sys.argv) == 3:
        CAMPAIGN, TARGET = sys.argv[1], sys.argv[2]
    cfg = f"{CAMPAIGN}__{TARGET}"
    GEO.mkdir(parents=True, exist_ok=True)
    water = water_polygon()
    obs, _ = load_observations(CAMPAIGN, TARGET)
    blocks = make_blocks(obs, BLOCK_KM)
    obs["segment"] = blocks
    xs, ys, X, Y, inwater = grid_for(obs, water)
    common_tags = {"variable": TARGET, "long_name": LABELS[TARGET], "units": UNITS[TARGET], "campaign": CAMPAIGN,
                   "obs_time_start_utc": str(obs.t_utc.min()), "obs_time_end_utc": str(obs.t_utc.max()),
                   "crs": f"EPSG:{EPSG}", "grid_cell_m": str(GRID_M), "support_max_dist_m": str(SUPPORT_M),
                   "model": "Gaussian process, Matern-3/2 + white noise, fitted in log(v+1) space" if TARGET in LOG_TARGETS
                   else "Gaussian process, Matern-3/2 + white noise", "model_version": MODEL_VERSION,
                   "provenance": PROVENANCE,
                   "caveat": "Model-grid size is not data resolution. Values are instrument fluorescence, not lab "
                             "chlorophyll-a or toxin. Cells beyond support distance or outside the water mask are NaN."}

    # observations export
    o = obs.copy()
    o["t_utc"] = o.t_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    g = to_wgs84_points(o.assign(variable=TARGET, units=UNITS[TARGET], campaign=CAMPAIGN, provenance=PROVENANCE))
    g.drop(columns=["x", "y"]).to_file(GEO / f"observations_{cfg}.geojson", driver="GeoJSON")

    # demo segments, chosen by fixed rules (not by how well the model does):
    #   hardest = largest within-segment SD of the target (most structure to reconstruct)
    #   central = segment containing the bin nearest the centroid of all bins (a mid-bay crossing)
    stats = obs.groupby("segment").value.agg(["std", "size"])
    stats = stats[stats["size"] >= 20]
    hardest = int(stats["std"].idxmax())
    c = obs[["x", "y"]].mean().values
    central = int(obs.segment.values[np.argmin(np.hypot(obs.x - c[0], obs.y - c[1]))])
    summary = {"campaign": CAMPAIGN, "target": TARGET, "units": UNITS[TARGET], "segments": {}}
    for label, b in [("hardest", hardest), ("central", central)]:
        te, tr = fold_split(obs, blocks, b, ALONG_BUFFER_M)
        gp, mu, sd, support, _ = reconstruct(obs, tr, X, Y, inwater)
        m, m_idw, cov80, pred, pred_t, sd_te = demo_figure(
            obs, b, te, tr, gp, X, Y, mu, sd, support, water, FIG / f"xray_demo_{cfg}_seg{b}.png", f"({label})")
        summary["segments"][label] = {"segment": b, "n_hidden": int(len(te)), "gp": m, "idw": m_idw,
                                      "gp_80pct_interval_hit_rate": cov80, "kernel": str(gp.gp.kernel_)}
        z = norm.ppf(0.9)
        h = obs.iloc[te].copy()
        h["t_utc"] = h.t_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        h = h.assign(truth=h.value, prediction=pred, error=pred - h.value.values,
                     lower80=inv(pred_t - z * sd_te, TARGET), upper80=inv(pred_t + z * sd_te, TARGET),
                     variable=TARGET, units=UNITS[TARGET], model_version=MODEL_VERSION)
        to_wgs84_points(h.drop(columns=["value"])).drop(columns=["x", "y"]).to_file(
            GEO / f"demo_holdout_{cfg}_seg{b}.geojson", driver="GeoJSON")
        write_geotiff(GEO / f"reconstruction_{cfg}_seg{b}.tif", xs, ys,
                      [inv(mu, TARGET), sd, inv(mu - z * sd, TARGET), inv(mu + z * sd, TARGET)],
                      ["mean", "sd_model_space", "lower80", "upper80"],
                      {**common_tags, "hidden_segment": str(b), "hidden_bins": str(len(te))})
        print(label, b, m, m_idw, cov80)

    # full-data reconstruction + sampling suggestions
    tr_all = np.arange(len(obs))
    gp, mu, sd, support, dist = reconstruct(obs, tr_all, X, Y, inwater)
    z = norm.ppf(0.9)
    write_geotiff(GEO / f"reconstruction_{cfg}_full.tif", xs, ys,
                  [inv(mu, TARGET), sd, inv(mu - z * sd, TARGET), inv(mu + z * sd, TARGET)],
                  ["mean", "sd_model_space", "lower80", "upper80"], {**common_tags, "hidden_segment": "none"})
    # candidates: supported water cells at least 500 m inside the (coarse) shoreline and >= 750 m from any bin
    inner = contains_xy(water.buffer(-500), X.ravel(), Y.ravel()).reshape(X.shape)
    cand_mask = (support & inner & (dist > 750)).ravel()
    G = np.column_stack([X.ravel(), Y.ravel()])
    cand = G[cand_mask]
    evalpts = G[support.ravel()]
    rng = np.random.default_rng(0)
    evalpts = evalpts[rng.choice(len(evalpts), size=min(3000, len(evalpts)), replace=False)]
    score = ivr_scores(gp, cand, evalpts)
    picks = []
    for _ in range(5):  # greedy, with 3 km exclusion so suggestions are spread out
        i = int(np.argmax(score))
        picks.append(i)
        score[np.hypot(cand[:, 0] - cand[i, 0], cand[:, 1] - cand[i, 1]) < 3000] = -np.inf
    cm, cs = gp.predict(cand[picks])
    cands = pd.DataFrame({"rank": np.arange(1, 6), "x": cand[picks, 0], "y": cand[picks, 1],
                          "predicted": inv(cm, TARGET), "sd_model_space": cs,
                          "dist_to_nearest_obs_m": cKDTree(obs[["x", "y"]].values).query(cand[picks])[0],
                          "method": "greedy integrated-variance-reduction (GP); suggestion, not proven optimal",
                          "variable": TARGET, "units": UNITS[TARGET], "model_version": MODEL_VERSION})
    to_wgs84_points(cands).drop(columns=["x", "y"]).to_file(GEO / f"sampling_candidates_{cfg}.geojson", driver="GeoJSON")
    summary["sampling_candidates"] = to_wgs84_points(cands).assign(
        lon=lambda d: d.geometry.x, lat=lambda d: d.geometry.y).drop(columns=["geometry", "x", "y"]).to_dict("records")

    # suggestion map
    fig, axes = plt.subplots(1, 2, figsize=(16, 10))
    ext = [X.min() - GRID_M / 2, X.max() + GRID_M / 2, Y.min() - GRID_M / 2, Y.max() + GRID_M / 2]
    v = obs.value.values
    lo, hi = np.percentile(v, [1, 99])
    cnorm = LogNorm(max(lo, 0.1), hi) if TARGET in LOG_TARGETS else Normalize(lo, hi)
    for ax, arr, ttl, cmap, nrm in [(axes[0], inv(mu, TARGET), "Reconstruction from all bins (GP mean)", "viridis", cnorm),
                                    (axes[1], sd, "GP SD + suggested next measurements (IVR)", "magma_r", None)]:
        gpd.GeoSeries([water], crs=EPSG).plot(ax=ax, color="#eef3f8", edgecolor="#8aa6c8", lw=0.6)
        im = ax.imshow(np.where(support, arr, np.nan), extent=ext, origin="upper", zorder=2, cmap=cmap, norm=nrm)
        plt.colorbar(im, ax=ax, shrink=0.6)
        ax.scatter(obs.x, obs.y, s=0.5, c="k", alpha=0.5, zorder=3)
        ax.set_xlim(obs.x.min() - 3000, obs.x.max() + 3000)
        ax.set_ylim(obs.y.min() - 3000, obs.y.max() + 3000)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(ttl, loc="left")
    axes[1].scatter(cands.x, cands.y, marker="*", s=260, color="#00b4d8", edgecolor="k", zorder=5)
    for _, r in cands.iterrows():
        axes[1].annotate(str(r["rank"]), (r.x, r.y), xytext=(6, 6), textcoords="offset points", fontsize=12, weight="bold")
    fig.suptitle(f"{CAMPAIGN} {LABELS[TARGET]}: grey/blank = no estimate (>3 km from evidence or outside water mask)")
    fig.tight_layout()
    fig.savefig(FIG / f"sampling_suggestions_{cfg}.png", dpi=110)
    plt.close(fig)

    # Experiment 7 replay
    rep = active_sampling_replay(obs, blocks)
    rep.to_csv(OUT / f"active_sampling_{cfg}.csv", index=False)
    asum = {"n_segments": int(len(rep)), "mean_mae_before": float(rep.mae_before.mean())}
    for k in ["random", "max_sd", "ivr", "max_dist"]:
        asum[f"mean_mae_after_{k}"] = float(rep[f"mae_{k}"].mean())
        asum[f"mean_rel_improvement_{k}"] = float(((rep.mae_before - rep[f"mae_{k}"]) / rep.mae_before).mean())
        if k != "random":
            asum[f"segments_{k}_beats_random"] = int((rep[f"mae_{k}"] < rep.mae_random).sum())
    summary["active_sampling_replay"] = asum
    print(json.dumps(asum, indent=1))
    fig, ax = plt.subplots(figsize=(7, 5))
    imp = {k: 100 * (rep.mae_before - rep[f"mae_{k}"]) / rep.mae_before for k in ["random", "max_sd", "ivr", "max_dist"]}
    ax.boxplot(list(imp.values()), tick_labels=["random\n(mean of 20)", "max GP SD", "IVR", "farthest from\nevidence"])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("reduction in hidden-segment MAE after 1 reveal (%)")
    ax.set_title(f"Active-sampling replay, {len(rep)} hidden segments\n{CAMPAIGN}, {LABELS[TARGET]}", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / f"active_sampling_{cfg}.png", dpi=110)
    plt.close(fig)

    p = OUT / "demo_summary.json"
    allsum = json.loads(p.read_text()) if p.exists() else {}
    allsum[cfg] = summary
    p.write_text(json.dumps(allsum, indent=2, default=str))


if __name__ == "__main__":
    main()
