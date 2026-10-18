"""Experiments A-C: leave-one-segment-out spatial cross-validation of interpolators, trained models and GP uncertainty.

For every (campaign, target) config, every contiguous along-track segment is held out in turn:
  standard : segment removed + `along_buffer_m` of same-track neighbours either side removed from training
  hard     : additionally removes every training bin within `spatial_buffer_m` of the held-out segment
             (crossing transects / return legs) - tests reconstruction from genuinely distant evidence
A random point-level split is also run as a leakage control - it is NOT a valid evaluation.

Outputs: outputs/cv_predictions_<cfg>.parquet, outputs/metrics/<cfg>.json, outputs/folds/<cfg>.csv
"""
import json
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

from xray_common import (OUT, PROC, UNITS, MODEL_VERSION, fit_gp, fit_hgb, fit_rf, fold_split, fwd, inv,
                         load_observations, make_blocks, metrics, predict_idw, predict_nn, predict_rf, coord_features)

CONFIGS = [
    # primary: closest campaign to July 2025 with 2-D cross-bay coverage
    dict(campaign="GreenBay_2025_Jun", target="chl_RFU_exo_tau"),
    dict(campaign="GreenBay_2025_Jun", target="bga_RFU_exo_tau"),
    dict(campaign="GreenBay_2025_Jun", target="turb_FNU_tau"),
    dict(campaign="GreenBay_2025_Jun", target="specCond_tau"),
    # replication on the other cross-bay campaign
    dict(campaign="GreenBay_2025_Apr", target="chl_RFU_exo_tau"),
    dict(campaign="GreenBay_2025_Apr", target="turb_FNU_tau"),
    # the July 2025 campaign itself, Green Bay portion only (river corridor excluded by the water mask)
    dict(campaign="Fox_2025_Jul", target="chl_RFU_exo_tau"),
    dict(campaign="Fox_2025_Jul", target="turb_FNU_tau"),
]
BLOCK_KM = 5.0
ALONG_BUFFER_M = 1000.0
SPATIAL_BUFFER_M = 1500.0
INTERVALS = (0.5, 0.8, 0.95)


def cfg_name(c):
    return f"{c['campaign']}__{c['target']}"


def run_fold(obs, tr, te, target, with_gp=True, seed=0):
    xy = obs[["x", "y"]].values
    v = obs["value"].values
    t = fwd(v, target)
    out = {}
    out["mean"] = np.full(len(te), v[tr].mean())
    out["nn"], dist = predict_nn(xy[tr], v[tr], xy[te])
    out["idw"] = predict_idw(xy[tr], v[tr], xy[te])
    rf = fit_rf(xy[tr], t[tr], seed)
    m, s = predict_rf(rf, xy[te])
    out["rf"], out["_rf_sd_t"], out["_rf_mu_t"] = inv(m, target), s, m
    out["hgb"] = inv(fit_hgb(xy[tr], t[tr], seed).predict(coord_features(xy[te])), target)
    if with_gp:
        gp = fit_gp(xy[tr], t[tr], n_max=800, seed=seed)
        m, s = gp.predict(xy[te])
        out["gp"], out["_gp_sd_t"], out["_gp_mu_t"] = inv(m, target), s, m
        out["_gp_kernel"] = str(gp.gp.kernel_)
    out["_dist_m"] = dist
    return out


def run_config(cfg, log):
    target = cfg["target"]
    obs, n_rows = load_observations(cfg["campaign"], target)
    blocks = make_blocks(obs, BLOCK_KM)
    res = {"campaign": cfg["campaign"], "target": target, "units": UNITS[target], "n_raw_rows_in_domain": int(n_rows),
           "n_bins_100m": int(len(obs)), "n_segments": int(len(np.unique(blocks))), "block_km": BLOCK_KM,
           "along_buffer_m": ALONG_BUFFER_M, "spatial_buffer_m": SPATIAL_BUFFER_M,
           "target_summary": {"mean": float(obs.value.mean()), "sd": float(obs.value.std()),
                              "p05": float(obs.value.quantile(.05)), "p95": float(obs.value.quantile(.95))},
           "schemes": {}}
    log(f"\n### {cfg_name(cfg)}: {n_rows} rows -> {len(obs)} bins, {res['n_segments']} segments")
    preds_all, fold_rows = [], []
    for scheme, sbuf in [("standard", 0.0), ("hard", SPATIAL_BUFFER_M)]:
        rows = []
        for b in np.unique(blocks):
            te, tr = fold_split(obs, blocks, b, ALONG_BUFFER_M, sbuf)
            if len(te) < 5 or len(tr) < 50:
                continue
            o = run_fold(obs, tr, te, target)
            df = pd.DataFrame({k: v for k, v in o.items() if k != "_gp_kernel"})
            df["idx"], df["block"], df["scheme"] = te, b, scheme
            df["y"] = obs.value.values[te]
            rows.append(df)
            fr = {"config": cfg_name(cfg), "scheme": scheme, "block": int(b), "n_test": len(te), "n_train": len(tr),
                  "test_sd": float(df.y.std()), "median_dist_to_train_m": float(np.median(o["_dist_m"])),
                  "gp_kernel": o.get("_gp_kernel")}
            for mdl in ["mean", "nn", "idw", "rf", "hgb", "gp"]:
                fr[f"MAE_{mdl}"] = float(np.abs(df[mdl] - df.y).mean())
            fold_rows.append(fr)
        P = pd.concat(rows, ignore_index=True)
        preds_all.append(P)
        sm = {"n_folds": int(P.block.nunique()), "n_test_points": int(len(P)), "models": {}}
        for mdl in ["mean", "nn", "idw", "rf", "hgb", "gp"]:
            sm["models"][mdl] = metrics(P.y, P[mdl])
            fm = pd.DataFrame([r for r in fold_rows if r["scheme"] == scheme and r["config"] == cfg_name(cfg)])
            sm["models"][mdl]["median_fold_MAE"] = float(fm[f"MAE_{mdl}"].median())
            sm["models"][mdl]["folds_won_vs_idw"] = int((fm[f"MAE_{mdl}"] < fm["MAE_idw"]).sum())
        # Experiment C: uncertainty on held-out segments (computed in model space, where the GP is Gaussian)
        tt = fwd(P.y.values, target)
        unc = {}
        for name, mu, sd in [("gp", P._gp_mu_t, P._gp_sd_t), ("rf_tree_spread", P._rf_mu_t, P._rf_sd_t)]:
            z = np.abs(tt - mu) / np.maximum(sd, 1e-9)
            unc[name] = {f"coverage_{int(q*100)}": float((z <= norm.ppf(0.5 + q / 2)).mean()) for q in INTERVALS}
            unc[name]["spearman_abs_err_vs_sd"] = float(spearmanr(np.abs(tt - mu), sd).statistic)
        unc["distance_to_nearest_obs"] = {
            "spearman_abs_err_vs_dist": float(spearmanr(np.abs(P.idw - P.y), P._dist_m).statistic),
            "median_m": float(P._dist_m.median()), "p90_m": float(P._dist_m.quantile(.9))}
        sm["uncertainty"] = unc
        res["schemes"][scheme] = sm
        log(f"  [{scheme}] folds={sm['n_folds']} n={sm['n_test_points']}  " + "  ".join(
            f"{k}:MAE={v['MAE']:.3g},R2={v['R2']:.2f}" for k, v in sm["models"].items()))
        log(f"     GP cov80={unc['gp']['coverage_80']:.2f} cov95={unc['gp']['coverage_95']:.2f} "
            f"rho={unc['gp']['spearman_abs_err_vs_sd']:.2f} | RFspread cov80={unc['rf_tree_spread']['coverage_80']:.2f} "
            f"| dist rho={unc['distance_to_nearest_obs']['spearman_abs_err_vs_dist']:.2f}")

    # Leakage control: random 20 % of bins held out (adjacent bins stay in training).
    rng = np.random.default_rng(0)
    te = rng.choice(len(obs), size=len(obs) // 5, replace=False)
    tr = np.setdiff1d(np.arange(len(obs)), te)
    o = run_fold(obs, tr, te, target, with_gp=False)
    res["random_split_LEAKY_control"] = {m: metrics(obs.value.values[te], o[m]) for m in ["mean", "nn", "idw", "rf", "hgb"]}
    log("  [random split, leaky control] " + "  ".join(
        f"{k}:R2={v['R2']:.2f}" for k, v in res["random_split_LEAKY_control"].items()))

    pd.concat(preds_all).to_parquet(OUT / f"cv_predictions_{cfg_name(cfg)}.parquet", index=False)
    return res, fold_rows


def main():
    """Each config writes its own files so configs can run as parallel processes; 05_report.py merges them."""
    only = sys.argv[1:]
    (OUT / "metrics").mkdir(exist_ok=True)
    (OUT / "folds").mkdir(exist_ok=True)
    for cfg in CONFIGS:
        if only and cfg_name(cfg) not in only and cfg["campaign"] not in only:
            continue
        name = cfg_name(cfg)
        log_f = open(OUT / "metrics" / f"{name}.log", "w")

        def log(s):
            print(s, flush=True)
            log_f.write(s + "\n")
            log_f.flush()

        t0 = time.time()
        res, fr = run_config(cfg, log)
        res["runtime_s"] = round(time.time() - t0, 1)
        res["model_version"] = MODEL_VERSION
        (OUT / "metrics" / f"{name}.json").write_text(json.dumps(res, indent=2))
        pd.DataFrame(fr).to_csv(OUT / "folds" / f"{name}.csv", index=False)
        log(f"  runtime {res['runtime_s']} s")


if __name__ == "__main__":
    main()
