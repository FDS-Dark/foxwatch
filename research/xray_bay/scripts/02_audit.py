"""Audit FLAMe_data.csv: campaigns, variable completeness, time/space coverage, survey geometry.

Outputs
  data/processed/flame_core.parquet  - all campaigns, core columns, projected to UTM 16N (EPSG:32616)
  outputs/audit_summary.json         - machine-readable audit
  figures/audit_tracks_<campaign>.png - survey tracks coloured by candidate targets
  figures/audit_overview.png         - all campaigns
"""
import json
import pathlib

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"
OUT = ROOT / "outputs"

# tau-corrected = hydraulic-lag + sensor-response corrected, i.e. best co-located with lat/lon (metadata Step 3)
CANDIDATES = {
    "chl_RFU_exo_tau": "Chlorophyll a fluorescence (EXO2), RFU",
    "bga_RFU_exo_tau": "Phycocyanin fluorescence (EXO2), RFU",
    "turb_FNU_tau": "Turbidity (EXO2), FNU",
    "specCond_tau": "Specific conductance (EXO2), uS/cm",
    "temp_exo_tau": "Water temperature (EXO2), degC",
    "fdom_QSU_exo_tau": "fDOM (EXO2), QSU",
    "BlueGreen_FP": "Blue-green algae (fluoroprobe), ug/L equiv.",
    "NO3_mgL": "Nitrate (SUNA), mg N/L",
}
CORE = ["DateTime_UTC", "id", "latitude", "longitude", "speed", "depth"] + list(CANDIDATES)
EPSG = 32616


def lakes():
    g = gpd.read_file(f"zip://{RAW / 'naturalearth' / 'ne_10m_lakes.zip'}")
    return g[g["name"].isin(["Lake Michigan", "Lake Winnebago"])].to_crs(EPSG)


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    path = RAW / "FLAMe_data.csv"
    header = pd.read_csv(path, nrows=0).columns.tolist()
    usecols = [c for c in CORE if c in header]
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    df["DateTime_UTC"] = pd.to_datetime(df["DateTime_UTC"], utc=True)
    n_raw = len(df)
    df = df.dropna(subset=["latitude", "longitude", "DateTime_UTC"])
    tr = Transformer.from_crs(4326, EPSG, always_xy=True)
    df["x"], df["y"] = tr.transform(df["longitude"].values, df["latitude"].values)
    df = df.sort_values(["id", "DateTime_UTC"]).reset_index(drop=True)

    # along-track distance and sampling interval, per campaign
    d = np.hypot(df.groupby("id")["x"].diff(), df.groupby("id")["y"].diff()).fillna(0)
    dt = df.groupby("id")["DateTime_UTC"].diff().dt.total_seconds()
    df["step_m"], df["dt_s"] = d, dt

    summary = {
        "source_file": str(path.name),
        "n_rows_raw": int(n_raw),
        "n_rows_with_position_time": int(len(df)),
        "columns_in_file": header,
        "crs_projected": f"EPSG:{EPSG}",
        "campaigns": {},
    }
    for cid, g in df.groupby("id"):
        days = sorted(g["DateTime_UTC"].dt.tz_convert("America/Chicago").dt.date.astype(str).unique())
        c = {
            "n_rows": int(len(g)),
            "start_utc": str(g["DateTime_UTC"].min()),
            "end_utc": str(g["DateTime_UTC"].max()),
            "local_days": days,
            "bbox_lonlat": [float(g.longitude.min()), float(g.latitude.min()), float(g.longitude.max()), float(g.latitude.max())],
            "median_dt_s": float(g["dt_s"].median()),
            "track_length_km": float(g["step_m"][g["step_m"] < 500].sum() / 1000),
            "n_rows_in_green_bay_lat_gt_44_52": int((g.latitude > 44.52).sum()),
            "variables": {},
        }
        for v in CANDIDATES:
            if v not in g:
                continue
            s = g[v]
            ok = s.notna()
            c["variables"][v] = {
                "n_valid": int(ok.sum()),
                "frac_valid": round(float(ok.mean()), 4),
                "min": None if not ok.any() else float(s.min()),
                "p05": None if not ok.any() else float(s.quantile(0.05)),
                "median": None if not ok.any() else float(s.median()),
                "p95": None if not ok.any() else float(s.quantile(0.95)),
                "max": None if not ok.any() else float(s.max()),
                "n_negative": int((s < 0).sum()),
            }
        summary["campaigns"][cid] = c

    df.drop(columns=["step_m", "dt_s"]).to_parquet(PROC / "flame_core.parquet", index=False)
    (OUT / "audit_summary.json").write_text(json.dumps(summary, indent=2))

    lk = lakes()
    # overview of all campaigns
    fig, ax = plt.subplots(figsize=(8, 10))
    lk.plot(ax=ax, color="#dbe9f6", edgecolor="#7a9cc6", lw=0.5)
    for cid, g in df.groupby("id"):
        ax.scatter(g.x[::20], g.y[::20], s=1, label=cid)
    ax.set_xlim(df.x.min() - 5e3, df.x.max() + 5e3)
    ax.set_ylim(df.y.min() - 5e3, df.y.max() + 5e3)
    ax.legend(markerscale=8, fontsize=8)
    ax.set_title("FLAMe survey tracks, all campaigns (UTM 16N)")
    ax.set_aspect("equal")
    fig.savefig(FIG / "audit_overview.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    plot_vars = ["chl_RFU_exo_tau", "bga_RFU_exo_tau", "turb_FNU_tau", "specCond_tau"]
    for cid, g in df.groupby("id"):
        fig, axes = plt.subplots(1, 4, figsize=(22, 7))
        for ax, v in zip(axes, plot_vars):
            lk.plot(ax=ax, color="#eef4fa", edgecolor="#7a9cc6", lw=0.5)
            if v in g and g[v].notna().any():
                gg = g[g[v].notna()]
                lo, hi = gg[v].quantile([0.02, 0.98])
                sc = ax.scatter(gg.x, gg.y, c=gg[v].clip(lo, hi), s=2, cmap="viridis")
                plt.colorbar(sc, ax=ax, shrink=0.6)
            ax.set_xlim(g.x.min() - 3e3, g.x.max() + 3e3)
            ax.set_ylim(g.y.min() - 3e3, g.y.max() + 3e3)
            ax.set_aspect("equal")
            ax.set_title(f"{cid}\n{CANDIDATES[v]}", fontsize=9)
            ax.tick_params(labelsize=6)
        fig.savefig(FIG / f"audit_tracks_{cid}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)

    # console summary
    for cid, c in summary["campaigns"].items():
        print(f"\n== {cid}: n={c['n_rows']} {c['local_days']} dt~{c['median_dt_s']}s track={c['track_length_km']:.0f} km GB_rows={c['n_rows_in_green_bay_lat_gt_44_52']}")
        for v, s in c["variables"].items():
            print(f"   {v:18s} valid={s['frac_valid']:.2f} med={s['median']} p05-p95={s['p05']}..{s['p95']} neg={s['n_negative']}")


if __name__ == "__main__":
    main()
