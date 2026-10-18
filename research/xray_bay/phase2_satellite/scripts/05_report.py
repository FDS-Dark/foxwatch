"""Summarise the matched-subset comparison: pooled + per-fold metrics, paired fold statistics, segment 32 diagnostics,
interval coverage. Outputs: outputs/satellite_model_comparison.csv, outputs/paired_folds.csv, outputs/metrics.json,
figures/hard_holdout_comparison.png
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr, wilcoxon

from p2_common import FIG, MODEL_VERSION, OUT, xc

RULES = ["glint_main", "glint_0701w24", "glint_0701", "glint_0628", "strict_main"]
RULE_DESC = {"glint_main": "PRIMARY: nearest same-survey scene, |lag|<=24 h, glint-corrected",
             "glint_0701w24": "post-hoc compliance check: 2025-07-01 scene only, |lag|<=24 h",
             "glint_0701": "sensitivity: 2025-07-01 scene only (lag -1.6..+26 h)",
             "glint_0628": "24-72 h tier: 2025-06-28 scene only (NOT time-matched)",
             "strict_main": "predeclared strict mask (B11<=0.03), same rule as primary"}
MODELS = ["nn", "idw", "rf_xy", "gp_xy", "rf_sat", "lin_sat", "rf_xysat", "rf_xysat_ext", "gp_resid"]
LOC_ONLY = ["nn", "idw", "rf_xy", "gp_xy"]
SAT_MODELS = ["rf_xysat", "rf_xysat_ext", "gp_resid"]
SEG = 32


def within_segment_r(P, model, min_sd_frac=0.05, min_n=10):
    """Phase 1 definition: median Pearson r inside each held-out segment, skipping nearly flat segments."""
    rs = []
    for _, g in P.groupby("block"):
        if len(g) < min_n or g.y.std() < min_sd_frac * abs(g.y.mean()) or g[model].std() == 0:
            continue
        rs.append(np.corrcoef(g.y, g[model])[0, 1])
    return (float(np.median(rs)) if rs else None), len(rs)


def fold_bootstrap_ratio(P, a, b, n=2000, seed=0):
    """95% CI of pooled MAE(a)/MAE(b) - 1, resampling whole folds."""
    rng = np.random.default_rng(seed)
    g = P.groupby("block")
    ea = g.apply(lambda d: np.abs(d[a] - d.y).sum(), include_groups=False).values
    eb = g.apply(lambda d: np.abs(d[b] - d.y).sum(), include_groups=False).values
    idx = rng.integers(0, len(ea), size=(n, len(ea)))
    r = ea[idx].sum(1) / eb[idx].sum(1) - 1
    return [float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))]


def coverage(P, mu_col, sd_col):
    tt = xc.fwd(P.y.values, "chl_RFU_exo_tau")
    z = np.abs(tt - P[mu_col]) / P[sd_col]
    err = np.abs(P[mu_col] - tt)
    return {f"coverage_{int(q * 100)}": float((z <= norm.ppf(0.5 + q / 2)).mean()) for q in (0.5, 0.8, 0.95)} | \
        {"spearman_abs_err_vs_sd": float(spearmanr(err, P[sd_col]).statistic)}


def main():
    rows, paired, out = [], [], {"model_version": MODEL_VERSION, "rules": {}}
    for rule in RULES:
        f = OUT / "cv" / f"{rule}.json"
        if not f.exists():
            continue
        res = json.loads(f.read_text())
        P_all = pd.read_parquet(OUT / "cv" / f"{rule}_predictions.parquet")
        out["rules"][rule] = {"description": RULE_DESC[rule], "n_bins_matched": res["n_bins_matched"], "schemes": {}}
        for scheme in ["hard", "standard"]:
            P = P_all[P_all.scheme == scheme]
            fold_mae = P.groupby("block").apply(lambda d: pd.Series({k: np.abs(d[k] - d.y).mean() for k in MODELS}),
                                                include_groups=False)
            best_loc = min(LOC_ONLY, key=lambda k: np.abs(P[k] - P.y).mean())
            sm = {"n_folds": int(P.block.nunique()), "n_test_bins": int(len(P)), "best_location_only": best_loc,
                  "models": {}, "paired": {}, "intervals": {}}
            for k in MODELS:
                m = xc.metrics(P.y, P[k])
                r, nseg = within_segment_r(P, k)
                m.update({"within_segment_median_r": r, "n_segments_with_shape": nseg,
                          "median_fold_MAE": float(fold_mae[k].median())})
                sm["models"][k] = m
                rows.append({"rule": rule, "scheme": scheme, "model": k, "n_folds": sm["n_folds"], "n_test": m["n"],
                             "MAE": m["MAE"], "RMSE": m["RMSE"], "R2": m["R2"], "bias": m["bias"],
                             "median_fold_MAE": m["median_fold_MAE"], "within_segment_median_r": r,
                             "MAE_change_vs_rf_xy_pct": 100 * (m["MAE"] / sm["models"].get("rf_xy", m)["MAE"] - 1)
                             if "rf_xy" in sm["models"] else None})
            for a in SAT_MODELS + ["rf_sat"]:
                for b in ["rf_xy", best_loc, "idw"]:
                    d = fold_mae[a] - fold_mae[b]
                    key = f"{a}_vs_{b}"
                    if key in sm["paired"]:
                        continue
                    p = wilcoxon(d).pvalue if (d != 0).any() else 1.0
                    sm["paired"][key] = {
                        "pooled_MAE_change_pct": 100 * (sm["models"][a]["MAE"] / sm["models"][b]["MAE"] - 1),
                        "fold_bootstrap_95ci_pct": [100 * x for x in fold_bootstrap_ratio(P, a, b)],
                        "folds_improved": int((d < 0).sum()), "folds_worse": int((d > 0).sum()),
                        "median_fold_diff_RFU": float(d.median()), "worst_fold_diff_RFU": float(d.max()),
                        "worst_fold": int(d.idxmax()), "wilcoxon_p_descriptive": float(p)}
                    paired.append({"rule": rule, "scheme": scheme, "a": a, "b": b, **sm["paired"][key]})
            sm["intervals"] = {"gp_xy": coverage(P, "gp_xy_mu_t", "gp_xy_sd_t"),
                               "gp_resid": coverage(P, "gp_resid_mu_t", "gp_resid_sd_t")}
            S = P[P.block == SEG]
            if len(S):
                sm["segment32"] = {"n_test": int(len(S)), "obs_mean": float(S.y.mean()), "obs_max": float(S.y.max()),
                                   "models": {k: {"MAE": float(np.abs(S[k] - S.y).mean()), "bias": float((S[k] - S.y).mean()),
                                                  "pred_max": float(S[k].max()),
                                                  "r": float(np.corrcoef(S.y, S[k])[0, 1]) if S[k].std() > 0 else None}
                                              for k in MODELS},
                                   "intervals": {"gp_xy": coverage(S, "gp_xy_mu_t", "gp_xy_sd_t"),
                                                 "gp_resid": coverage(S, "gp_resid_mu_t", "gp_resid_sd_t")}}
            out["rules"][rule]["schemes"][scheme] = sm
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "satellite_model_comparison.csv", index=False)
    pd.DataFrame(paired).to_csv(OUT / "paired_folds.csv", index=False)
    (OUT / "metrics.json").write_text(json.dumps(out, indent=2))

    pd.set_option("display.width", 250)
    print(T.pivot_table(index=["rule", "scheme"], columns="model", values="MAE")[MODELS].round(3).to_string())
    print(T.pivot_table(index=["rule", "scheme"], columns="model", values="within_segment_median_r")[MODELS].round(2).to_string())
    print(pd.DataFrame(paired)[lambda d: d.b != "idw"].round(3).to_string())
    for rule, r in out["rules"].items():
        print(rule, {s: (v["n_folds"], v["best_location_only"]) for s, v in r["schemes"].items()})
        s32 = r["schemes"]["hard"].get("segment32")
        if s32:
            print("  seg32 hard", s32["n_test"], "obs mean/max", round(s32["obs_mean"], 2), round(s32["obs_max"], 2),
                  {k: (round(v["MAE"], 2), round(v["bias"], 2), round(v["pred_max"], 2)) for k, v in s32["models"].items()})
        print("  intervals hard", r["schemes"]["hard"]["intervals"])

    # figure: hard-scheme MAE by model and rule + per-fold paired scatter for the primary rule
    fig, axs = plt.subplots(1, 3, figsize=(19, 6), gridspec_kw={"width_ratios": [1.6, 1, 1]})
    rules = [r for r in RULES if r in out["rules"]]
    w = 0.8 / len(rules)
    for i, rule in enumerate(rules):
        t = T[(T.rule == rule) & (T.scheme == "hard")].set_index("model").loc[MODELS]
        n = out["rules"][rule]["schemes"]["hard"]["n_folds"]
        axs[0].bar(np.arange(len(MODELS)) + (i - (len(rules) - 1) / 2) * w, t.MAE, width=w,
                   label=f"{rule} ({n} folds)")
    axs[0].set_xticks(np.arange(len(MODELS)))
    axs[0].set_xticklabels(MODELS, rotation=30)
    axs[0].axvspan(-0.5, 3.5, color="0.92", zorder=0)
    axs[0].text(1.5, axs[0].get_ylim()[1] * 0.97, "location only", ha="center", va="top", fontsize=9)
    axs[0].set_ylabel("pooled MAE on held-out bins (RFU)")
    axs[0].set_title("Hard spatial holdout, each rule on its own matched subset\n(compare models WITHIN a rule, not across)")
    axs[0].legend(fontsize=8)
    P = pd.read_parquet(OUT / "cv" / "glint_main_predictions.parquet")
    P = P[P.scheme == "hard"]
    fm = P.groupby("block").apply(lambda d: pd.Series({k: np.abs(d[k] - d.y).mean() for k in MODELS}), include_groups=False)
    for a, (xk, yk) in zip(axs[1:], [("rf_xy", "rf_xysat"), ("gp_xy", "gp_resid")]):
        lim = [0, fm[[xk, yk]].values.max() * 1.05]
        a.plot(lim, lim, "k-", lw=0.7)
        a.scatter(fm[xk], fm[yk], s=25)
        for b, r in fm.iterrows():
            if b == SEG or abs(r[yk] - r[xk]) > 0.4:
                a.annotate(str(b), (r[xk], r[yk]), fontsize=8, color="crimson" if b == SEG else "k")
        a.set_xlabel(f"fold MAE, {xk} (location only), RFU")
        a.set_ylabel(f"fold MAE, {yk} (with satellite), RFU")
        a.set_title(f"primary rule, hard scheme: below line = satellite helps\n"
                    f"{(fm[yk] < fm[xk]).sum()}/{len(fm)} folds improved", fontsize=10)
        a.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(FIG / "hard_holdout_comparison.png", dpi=110)


if __name__ == "__main__":
    main()
