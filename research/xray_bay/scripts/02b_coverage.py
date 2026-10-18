"""Coverage audit: what fraction of the surveyed water body lies within d km of a measurement?

Dense along-track sampling is not dense areal coverage. Domain = Natural Earth Lake Michigan polygon clipped to
the campaign's bounding box (+3 km), on a 250 m grid. Output: outputs/coverage_audit.json
"""
import json

import numpy as np
from scipy.spatial import cKDTree
from shapely import contains_xy

from xray_common import OUT, load_observations, water_polygon

CAMPAIGNS = ["GreenBay_2025_Jun", "GreenBay_2025_Apr", "Fox_2025_Jul", "Fox_2024_Jul", "Fox_2024_Aug"]


def main():
    w = water_polygon()
    res = {}
    for c in CAMPAIGNS:
        obs, n = load_observations(c, "chl_RFU_exo_tau")
        xs = np.arange(obs.x.min() - 3000, obs.x.max() + 3000, 250)
        ys = np.arange(obs.y.min() - 3000, obs.y.max() + 3000, 250)
        X, Y = np.meshgrid(xs, ys)
        m = contains_xy(w, X.ravel(), Y.ravel())
        G = np.column_stack([X.ravel()[m], Y.ravel()[m]])
        d, _ = cKDTree(obs[["x", "y"]].values).query(G)
        res[c] = {"n_raw_rows_in_green_bay": int(n), "n_bins_100m": int(len(obs)),
                  "track_km_in_bay": round(float(obs.along_m.max() / 1000), 1),
                  "water_area_in_bbox_km2": round(float(m.sum() * 0.0625), 1),
                  **{f"frac_water_within_{k}km": round(float((d <= k * 1000).mean()), 3) for k in (0.5, 1, 2, 3, 5)},
                  "median_dist_water_to_obs_km": round(float(np.median(d) / 1000), 2),
                  "max_dist_water_to_obs_km": round(float(d.max() / 1000), 2),
                  "days_utc": sorted(obs.t_utc.dt.strftime("%Y-%m-%d").unique().tolist())}
        print(c, res[c])
    (OUT / "coverage_audit.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
