"""Summarise CV results into tables/figures used by RESULTS.md.

Adds a stricter view than pooled R2: pooled R2 rewards getting the *level* of each segment right (mouth vs. open bay).
`within_segment_r` asks whether the model also reproduces the *shape* along a hidden segment.

Outputs: outputs/metrics.json (merged), outputs/cv_folds.csv, outputs/results_table.csv, outputs/metrics_summary.json, figures/cv_skill_<scheme>.png
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from xray_common import FIG, OUT

MODELS = ["mean", "nn", "idw", "rf", "hgb", "gp"]
NAMES = {"mean": "global mean", "nn": "nearest neighbour", "idw": "IDW (p=2, k=12)", "rf": "random forest",
         "hgb": "gradient boosting", "gp": "Gaussian process"}


def within_segment_r(P, model, min_sd_frac=0.05):
    """Median Pearson r between prediction and truth inside each hidden segment.

    Segments that are nearly flat (SD < min_sd_frac * segment mean) have no shape to reproduce and are skipped.
    """
    rs = []
    for _, g in P.groupby("block"):
        if len(g) < 10 or g.y.std() < min_sd_frac * abs(g.y.mean()) or g[model].std() == 0:
            continue
        rs.append(np.corrcoef(g.y, g[model])[0, 1])
    return (float(np.median(rs)) if rs else None), len(rs)


def main():
    M = {"model_version": None, "configs": {}}
    for f in sorted((OUT / "metrics").glob("*.json")):
        r = json.loads(f.read_text())
        M["model_version"] = r["model_version"]
        M["configs"][f.stem] = r
    (OUT / "metrics.json").write_text(json.dumps(M, indent=2))
    pd.concat([pd.read_csv(f) for f in sorted((OUT / "folds").glob("*.csv"))]).to_csv(OUT / "cv_folds.csv", index=False)
    rows = []
    for cfg, res in M["configs"].items():
        P_all = pd.read_parquet(OUT / f"cv_predictions_{cfg}.parquet")
        for scheme, sm in res["schemes"].items():
            P = P_all[P_all.scheme == scheme]
            for mdl in MODELS:
                m = sm["models"][mdl]
                r, nseg = within_segment_r(P, mdl) if mdl != "mean" else (None, 0)
                rows.append({"config": cfg, "campaign": res["campaign"], "target": res["target"], "units": res["units"],
                             "scheme": scheme, "model": mdl, "n_folds": sm["n_folds"], "n_test": m["n"],
                             "MAE": m["MAE"], "RMSE": m["RMSE"], "R2": m["R2"], "bias": m["bias"],
                             "median_fold_MAE": m["median_fold_MAE"], "folds_won_vs_idw": m["folds_won_vs_idw"],
                             "within_segment_median_r": r, "n_segments_with_shape": nseg})
            leaky = res["random_split_LEAKY_control"]
            for mdl, m in leaky.items():
                rows.append({"config": cfg, "campaign": res["campaign"], "target": res["target"], "units": res["units"],
                             "scheme": "random_LEAKY", "model": mdl, "n_test": m["n"], "MAE": m["MAE"],
                             "RMSE": m["RMSE"], "R2": m["R2"], "bias": m["bias"]})
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "results_table.csv", index=False)

    # compact summary: per config/scheme, best model vs IDW + uncertainty calibration
    summ = {"model_version": M["model_version"], "configs": {}}
    for cfg, res in M["configs"].items():
        d = {"campaign": res["campaign"], "target": res["target"], "units": res["units"],
             "n_bins": res["n_bins_100m"], "n_segments": res["n_segments"], "target_summary": res["target_summary"]}
        for scheme, sm in res["schemes"].items():
            t = T[(T.config == cfg) & (T.scheme == scheme)].set_index("model")
            best = t.drop("mean").MAE.idxmin()
            d[scheme] = {
                "best_model": best, "best_MAE": t.loc[best, "MAE"], "best_R2": t.loc[best, "R2"],
                "idw_MAE": t.loc["idw", "MAE"], "idw_R2": t.loc["idw", "R2"],
                "nn_MAE": t.loc["nn", "MAE"], "mean_MAE": t.loc["mean", "MAE"],
                "best_vs_idw_MAE_change_pct": 100 * (t.loc[best, "MAE"] / t.loc["idw", "MAE"] - 1),
                "gp_coverage_80": sm["uncertainty"]["gp"]["coverage_80"],
                "gp_coverage_95": sm["uncertainty"]["gp"]["coverage_95"],
                "gp_spearman_abs_err_vs_sd": sm["uncertainty"]["gp"]["spearman_abs_err_vs_sd"],
                "rf_spread_coverage_80": sm["uncertainty"]["rf_tree_spread"]["coverage_80"],
                "dist_spearman_abs_err": sm["uncertainty"]["distance_to_nearest_obs"]["spearman_abs_err_vs_dist"],
            }
        d["random_LEAKY_idw_R2"] = res["random_split_LEAKY_control"]["idw"]["R2"]
        summ["configs"][cfg] = d
    (OUT / "metrics_summary.json").write_text(json.dumps(summ, indent=2))

    for scheme in ["standard", "hard"]:
        t = T[T.scheme == scheme]
        cfgs = list(M["configs"])
        fig, ax = plt.subplots(figsize=(12, 0.6 * len(cfgs) + 2))
        w = 0.14
        for i, mdl in enumerate(MODELS[1:]):
            vals = [t[(t.config == c) & (t.model == mdl)].R2.values[0] for c in cfgs]
            ax.barh(np.arange(len(cfgs)) + (i - 2) * w, vals, height=w, label=NAMES[mdl])
        leaky = [T[(T.config == c) & (T.scheme == "random_LEAKY") & (T.model == "idw")].R2.values[0] for c in cfgs]
        ax.scatter(leaky, np.arange(len(cfgs)), marker="|", s=300, color="k", label="IDW, random split (leaky)", zorder=5)
        ax.set_yticks(np.arange(len(cfgs)))
        ax.set_yticklabels([c.replace("__", "\n") for c in cfgs], fontsize=8)
        ax.axvline(0, color="k", lw=0.6)
        ax.set_xlim(-0.3, 1.0)
        ax.set_xlabel("pooled R² on held-out segments")
        ax.set_title(f"Spatial leave-one-segment-out CV ({scheme} scheme)")
        ax.legend(fontsize=8, loc="lower left")
        ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(FIG / f"cv_skill_{scheme}.png", dpi=110)
        plt.close(fig)

    pd.set_option("display.width", 250)
    show = T[T.scheme != "random_LEAKY"].pivot_table(index=["config", "scheme"], columns="model", values="MAE")[MODELS]
    print(show.round(3).to_string())
    print(T[T.scheme != "random_LEAKY"].pivot_table(index=["config", "scheme"], columns="model", values="R2")[MODELS].round(2).to_string())
    print(T[T.scheme != "random_LEAKY"].pivot_table(index=["config", "scheme"], columns="model",
                                                     values="within_segment_median_r")[MODELS[1:]].round(2).to_string())


if __name__ == "__main__":
    main()
