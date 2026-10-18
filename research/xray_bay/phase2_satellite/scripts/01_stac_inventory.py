"""G0: Sentinel-2 L2A discovery over the actual survey footprint.

Queries Earth Search (`sentinel-2-c1-l2a`, plus `sentinel-2-l2a` for cross-check) for 2025-06-26..07-04 (+-3 d sensitivity
window around the 2025-06-30..07-01 survey), records every item, its acquisition time, footprint and cloud metadata,
and the time lag to the survey. Outputs: outputs/scene_inventory.csv, outputs/stac_items/<id>.json,
figures/acquisition_timeline.png
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
from shapely.geometry import box, shape

from p2_common import AOI, CAMPAIGN, COLLECTION, FIG, OUT, STAC, TARGET, xc

WINDOW = "2025-06-26T00:00:00Z/2025-07-04T23:59:59Z"


def search(collection):
    body = {"collections": [collection], "bbox": list(AOI), "datetime": WINDOW, "limit": 200}
    r = requests.post(f"{STAC}/search", json=body, timeout=60)
    r.raise_for_status()
    return r.json()["features"]


def main():
    obs, _ = xc.load_observations(CAMPAIGN, TARGET)
    t0, t1 = obs.t_utc.min(), obs.t_utc.max()
    aoi = box(*AOI)
    (OUT / "stac_items").mkdir(exist_ok=True)
    rows = []
    for coll in [COLLECTION, "sentinel-2-l2a"]:
        for f in search(coll):
            p = f["properties"]
            t = pd.Timestamp(p["datetime"])
            fp = shape(f["geometry"])
            if coll == COLLECTION:
                (OUT / "stac_items" / f"{f['id']}.json").write_text(json.dumps(f, indent=1))
            lag = 0.0 if t0 <= t <= t1 else min(abs((t - t0).total_seconds()), abs((t - t1).total_seconds())) / 3600
            rows.append({
                "collection": coll, "id": f["id"], "datetime_utc": t, "platform": p.get("platform"),
                "mgrs": p.get("grid:code"), "processing_baseline": p.get("s2:processing_baseline"),
                "scene_cloud_pct": p.get("eo:cloud_cover"), "cloud_shadow_pct": p.get("s2:cloud_shadow_percentage"),
                "thin_cirrus_pct": p.get("s2:thin_cirrus_percentage"), "water_pct": p.get("s2:water_percentage"),
                "nodata_pct": p.get("s2:nodata_pixel_percentage"), "sun_elev": p.get("view:sun_elevation"),
                "aoi_overlap_frac": fp.intersection(aoi).area / aoi.area,
                "survey_overlap_or_gap_h": round(lag, 2),
                "assets": ",".join(sorted(f["assets"])),
            })
    inv = pd.DataFrame(rows).sort_values(["collection", "datetime_utc", "mgrs"])
    inv.to_csv(OUT / "scene_inventory.csv", index=False)
    print(inv.drop(columns="assets").to_string())

    c1 = inv[inv.collection == COLLECTION]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    for d, g in obs.groupby(obs.t_utc.dt.date):
        ax.axvspan(g.t_utc.min(), g.t_utc.max(), color="tab:blue", alpha=0.25)
    ax.plot([], [], color="tab:blue", alpha=0.4, lw=8, label="boat survey (100 m bins)")
    for _, r in c1.iterrows():
        col = "tab:green" if r.mgrs == "MGRS-16TDQ" else "tab:gray"
        ax.scatter(r.datetime_utc, r.scene_cloud_pct, color=col, s=50, zorder=3)
        ax.annotate(f"{r.platform[-2:].upper()} {r.mgrs[-5:]}\n{r.scene_cloud_pct:.0f}%", (r.datetime_utc, r.scene_cloud_pct),
                    fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.scatter([], [], color="tab:green", label="16TDQ (contains whole survey)")
    ax.scatter([], [], color="tab:gray", label="16TDR (north of 45.06 N only)")
    ax.set_ylabel("scene-wide cloud % (metadata only)")
    ax.set_title("Sentinel-2 L2A acquisitions (Earth Search sentinel-2-c1-l2a) vs. GreenBay_2025_Jun survey")
    ax.legend(fontsize=8, loc="upper right")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "acquisition_timeline.png", dpi=120)


if __name__ == "__main__":
    main()
