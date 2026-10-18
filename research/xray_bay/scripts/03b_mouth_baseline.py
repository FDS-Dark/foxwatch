"""Skeptic's baseline: predict the target from distance to the Fox River mouth alone (1-D, monotone).

If this matches the spatial models, their pooled R2 mostly reflects the plume gradient, not spatial reconstruction.
Same folds/buffers as 03_experiment.py. Output: outputs/mouth_baseline.json
"""
import json
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer
from sklearn.isotonic import IsotonicRegression

from xray_common import EPSG, OUT, fold_split, fwd, inv, load_observations, make_blocks, metrics

MOUTH_LONLAT = (-88.003, 44.537)  # Fox River at Green Bay shoreline
CFGS = [("GreenBay_2025_Jun", "chl_RFU_exo_tau"), ("GreenBay_2025_Jun", "bga_RFU_exo_tau"),
        ("GreenBay_2025_Jun", "turb_FNU_tau"), ("GreenBay_2025_Jun", "specCond_tau"),
        ("GreenBay_2025_Apr", "chl_RFU_exo_tau"), ("GreenBay_2025_Apr", "turb_FNU_tau"),
        ("Fox_2025_Jul", "chl_RFU_exo_tau"), ("Fox_2025_Jul", "turb_FNU_tau")]


def main():
    mx, my = Transformer.from_crs(4326, EPSG, always_xy=True).transform(*MOUTH_LONLAT)
    out = {}
    for campaign, target in CFGS:
        obs, _ = load_observations(campaign, target)
        d = np.hypot(obs.x - mx, obs.y - my).values
        t = fwd(obs.value.values, target)
        blocks = make_blocks(obs, 5.0)
        res = {}
        for scheme, sbuf in [("standard", 0.0), ("hard", 1500.0)]:
            ys, ps = [], []
            for b in np.unique(blocks):
                te, tr = fold_split(obs, blocks, b, 1000.0, sbuf)
                if len(te) < 5 or len(tr) < 50:
                    continue
                # direction of monotonicity learned from training data only
                inc = np.corrcoef(d[tr], t[tr])[0, 1] > 0
                m = IsotonicRegression(increasing=inc, out_of_bounds="clip").fit(d[tr], t[tr])
                ys.append(obs.value.values[te])
                ps.append(inv(m.predict(d[te]), target))
            res[scheme] = metrics(np.concatenate(ys), np.concatenate(ps))
        out[f"{campaign}__{target}"] = res
        print(campaign, target, {k: (round(v["MAE"], 3), round(v["R2"], 2)) for k, v in res.items()})
    (OUT / "mouth_baseline.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
