"""G2/G3: coordinate-only vs coordinate+satellite models on identical matched bins and identical Phase 1 folds.

Folds: Phase 1 definition (5 km contiguous segments; standard = segment + 1 km same-track buffer; hard = also every bin
within 1.5 km of the segment) computed on the FULL 2,497-bin survey, then intersected with the satellite-matched subset.
So the exclusion zones are exactly Phase 1's, and every model in a fold sees the same train/test bins.
A fold is eligible if it keeps >= 10 matched test bins and >= 100 matched training bins (fixed before running).

Models (all trained on log(RFU + 1) like Phase 1, except IDW/NN which interpolate RFU directly):
  idw, nn        : Phase 1 interpolators, matched training bins only
  rf_xy          : Phase 1 RF (coordinates + 7 oblique rotations), same hyperparameters  -> FAIR CONTROL
  rf_xysat       : rf_xy features + B03, B04, B05, NDCI (glint-corrected)              -> satellite-enhanced
  rf_xysat_ext   : + B02, B06, B07, B8A, red/green ratio
  rf_sat         : satellite features only (B03, B04, B05, NDCI) - is there spectral signal at all?
  gp_xy          : Phase 1 GP (Matern 3/2 + white, <= 800 subsample)
  gp_resid       : rf_sat-free variant: GP on coordinates fitted to residuals of a linear model on the 4 satellite
                   features (training-fold standardisation) - 'regression kriging'
Usage: 04_experiment.py [rule ...]   rules: glint_main (primary), glint_0701, glint_0628, strict_main
Outputs: outputs/cv/<rule>_predictions.parquet, outputs/cv/<rule>_folds.csv, outputs/cv/<rule>.json
"""
import json
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from p2_common import MODEL_VERSION, OUT, xc

BLOCK_KM, ALONG_BUFFER_M, SPATIAL_BUFFER_M = 5.0, 1000.0, 1500.0
MIN_TEST, MIN_TRAIN = 10, 100
SAT4 = ["B03", "B04", "B05", "NDCI"]
SAT_EXT = SAT4 + ["B02", "B06", "B07", "B8A", "RG"]
TARGET = "chl_RFU_exo_tau"


def rf(X, t, seed=0):
    m = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.5, n_jobs=xc.N_JOBS, random_state=seed)
    return m.fit(X, t)


def run_fold(D, tr, te, sat4, satx, seed=0):
    xy, v = D[["x", "y"]].values, D["chl_RFU"].values
    t = xc.fwd(v, TARGET)
    C = xc.coord_features(xy)
    out = {}
    out["nn"], dist = xc.predict_nn(xy[tr], v[tr], xy[te])
    out["idw"] = xc.predict_idw(xy[tr], v[tr], xy[te])
    out["rf_xy"] = xc.inv(rf(C[tr], t[tr], seed).predict(C[te]), TARGET)
    Xs = np.column_stack([C, sat4])
    out["rf_xysat"] = xc.inv(rf(Xs[tr], t[tr], seed).predict(Xs[te]), TARGET)
    Xe = np.column_stack([C, satx])
    out["rf_xysat_ext"] = xc.inv(rf(Xe[tr], t[tr], seed).predict(Xe[te]), TARGET)
    out["rf_sat"] = xc.inv(rf(sat4[tr], t[tr], seed).predict(sat4[te]), TARGET)
    gp = xc.fit_gp(xy[tr], t[tr], n_max=800, seed=seed)
    m, s = gp.predict(xy[te])
    out["gp_xy"], out["_gp_xy_sd_t"], out["_gp_xy_mu_t"] = xc.inv(m, TARGET), s, m
    mu, sd = sat4[tr].mean(0), sat4[tr].std(0) + 1e-12  # training-fold standardisation only
    lin = LinearRegression().fit((sat4[tr] - mu) / sd, t[tr])
    trend_tr, trend_te = lin.predict((sat4[tr] - mu) / sd), lin.predict((sat4[te] - mu) / sd)
    gpr = xc.fit_gp(xy[tr], t[tr] - trend_tr, n_max=800, seed=seed)
    m2, s2 = gpr.predict(xy[te])
    out["gp_resid"], out["_gp_resid_sd_t"], out["_gp_resid_mu_t"] = xc.inv(m2 + trend_te, TARGET), s2, m2 + trend_te
    out["lin_sat"] = xc.inv(trend_te, TARGET)
    out["_dist_m"] = dist
    return out


MODELS = ["nn", "idw", "rf_xy", "rf_xysat", "rf_xysat_ext", "rf_sat", "lin_sat", "gp_xy", "gp_resid"]


def run_rule(rule, log):
    M = pd.read_parquet(OUT / "matched_bins.parquet")
    obs, _ = xc.load_observations("GreenBay_2025_Jun", TARGET)
    assert len(obs) == len(M) and np.allclose(obs.x, M.x) and np.allclose(obs.value, M.chl_RFU), "bins differ from Phase 1"
    blocks = xc.make_blocks(M, BLOCK_KM)
    matched = M[f"matched_{rule}"].values
    sat4 = M[[f"{b}_{rule}" for b in SAT4]].values
    satx = M[[f"{b}_{rule}" for b in SAT_EXT]].values
    res = {"rule": rule, "model_version": MODEL_VERSION, "n_bins_full": int(len(M)), "n_bins_matched": int(matched.sum()),
           "min_test": MIN_TEST, "min_train": MIN_TRAIN, "sat4": SAT4, "sat_ext": SAT_EXT, "schemes": {}}
    preds, folds = [], []
    for scheme, sbuf in [("hard", SPATIAL_BUFFER_M), ("standard", 0.0)]:
        rows = []
        for b in np.unique(blocks):
            te_full, tr_full = xc.fold_split(M, blocks, b, ALONG_BUFFER_M, sbuf)
            te, tr = te_full[matched[te_full]], tr_full[matched[tr_full]]
            row = {"rule": rule, "scheme": scheme, "block": int(b), "n_test_full": len(te_full), "n_test": len(te),
                   "n_train_full": len(tr_full), "n_train": len(tr),
                   "abs_lag_h_test_median": float(np.nanmedian(np.abs(M[f"lag_h_{rule}"].values[te]))) if len(te) else None}
            if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
                row["eligible"] = False
                folds.append(row)
                continue
            row["eligible"] = True
            o = run_fold(M, tr, te, sat4, satx, seed=int(b))
            y = M.chl_RFU.values[te]
            P = pd.DataFrame({"rule": rule, "scheme": scheme, "block": b, "idx": te, "x": M.x.values[te], "y_m": M.y.values[te],
                              "y": y, **{k: o[k] for k in MODELS}, "dist_m": o["_dist_m"],
                              "gp_xy_sd_t": o["_gp_xy_sd_t"], "gp_xy_mu_t": o["_gp_xy_mu_t"],
                              "gp_resid_sd_t": o["_gp_resid_sd_t"], "gp_resid_mu_t": o["_gp_resid_mu_t"]})
            preds.append(P)
            for k in MODELS:
                row[f"MAE_{k}"] = float(np.abs(o[k] - y).mean())
            folds.append(row)
            rows.append(row)
        log(f"{rule} {scheme}: {len(rows)} eligible folds")
    P = pd.concat(preds, ignore_index=True)
    F = pd.DataFrame(folds)
    (OUT / "cv").mkdir(exist_ok=True)
    P.to_parquet(OUT / "cv" / f"{rule}_predictions.parquet")
    F.to_csv(OUT / "cv" / f"{rule}_folds.csv", index=False)
    for scheme in ["hard", "standard"]:
        Ps = P[P.scheme == scheme]
        res["schemes"][scheme] = {"n_eligible_folds": int(Ps.block.nunique()), "n_test_bins": int(len(Ps)),
                                  "models": {k: xc.metrics(Ps.y, Ps[k]) for k in MODELS}}
    (OUT / "cv" / f"{rule}.json").write_text(json.dumps(res, indent=2))
    return res


def main():
    rules = sys.argv[1:] or ["glint_main", "glint_0701", "glint_0628", "strict_main"]
    for rule in rules:
        t0 = time.time()
        res = run_rule(rule, print)
        for s, sm in res["schemes"].items():
            print(rule, s, sm["n_eligible_folds"], "folds", sm["n_test_bins"], "bins")
            print("   " + "  ".join(f"{k}={m['MAE']:.3f}" for k, m in sm["models"].items()))
        print(f"{rule} done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
