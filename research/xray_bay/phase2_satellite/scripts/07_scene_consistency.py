"""Diagnostic: are the 2025-06-30 and 2025-07-01 features radiometrically consistent where both scenes are valid?
And how strongly does each scene's NDCI/B04 rank-correlate with fluorescence, by scene source? (descriptive only)
Output: outputs/scene_consistency.json, figures/scene_consistency.png
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from p2_common import FIG, OUT

M = pd.read_parquet(OUT / "matched_bins.parquet")
both = M.matched_glint_0701 & M.scene_glint_main.eq("S2A_T16TDQ_20250630T164706_L2A")
res = {"n_bins_both_valid": int(both.sum())}
fig, axs = plt.subplots(1, 4, figsize=(18, 4.5))
for a, b in zip(axs, ["B03", "B04", "B05", "NDCI"]):
    x, y = M.loc[both, f"{b}_glint_0701"], M.loc[both, f"{b}_glint_main"]
    a.scatter(x, y, s=4, c=M.loc[both, "chl_RFU"], cmap="viridis")
    lo, hi = np.nanmin([x.min(), y.min()]), np.nanmax([x.max(), y.max()])
    a.plot([lo, hi], [lo, hi], "k-", lw=0.6)
    a.set_xlabel(f"{b}, 07-01 S2C"); a.set_ylabel(f"{b}, 06-30 S2A")
    r = spearmanr(x, y).statistic
    a.set_title(f"{b}: Spearman {r:.2f}, median diff {np.median(y - x):+.4f}")
    res[b] = {"spearman_between_scenes": float(r), "median_0630_minus_0701": float(np.median(y - x))}
fig.suptitle(f"Same bins seen by both scenes ({both.sum()} bins; colour = boat fluorescence)")
fig.tight_layout()
fig.savefig(FIG / "scene_consistency.png", dpi=100)
for src, g in M[M.matched_glint_main].groupby("scene_glint_main"):
    res[f"spearman_vs_RFU_{src[:3]}"] = {b: float(spearmanr(g[f"{b}_glint_main"], g.chl_RFU).statistic)
                                        for b in ["B03", "B04", "B05", "NDCI", "RG"]} | {"n": int(len(g))}
g = M[M.matched_glint_0701]
res["spearman_vs_RFU_0701_all"] = {b: float(spearmanr(g[f"{b}_glint_0701"], g.chl_RFU).statistic)
                                   for b in ["B03", "B04", "B05", "NDCI", "RG"]} | {"n": int(len(g))}
(OUT / "scene_consistency.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
