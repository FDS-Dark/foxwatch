"""G1 + G2: per-scene water-quality mask, then match satellite features to the Phase 1 100 m bins.

Mask (fixed before looking at any fluorescence values):
  valid water pixel = all bands finite
                      & SCL not in {0 no-data, 1 saturated, 3 cloud shadow, 8/9 cloud, 10 cirrus, 11 snow}
                      & CLD (cloud probability) <= 10 %
                      & MNDWI = (B03 - B11)/(B03 + B11) > 0        (spectrally water; SCL alone mislabels turbid water)
                      & B11 <= 0.03                                (haze / thin cloud / glint residual screen)
                      & >= 200 m from any pixel failing the above  (shoreline adjacency and cloud edges/shadows)
Bin feature = median of valid pixels in the 5 x 5 (100 m) window centred on the bin; requires >= 13/25 valid.

DOCUMENTED DEVIATION (made after the G1 pixel audit, before any comparison with fluorescence):
  The B11 <= 0.03 screen rejected 88 % of track bins on the near-cloud-free 2025-07-01 scene. Water B11 there is a smooth
  0.04-0.08 field with a NE-SW gradient - sun glint / aerosol (sun zenith 24 deg, view zenith 9 deg), not cloud.
  Two mask variants are therefore produced:
    strict : as predeclared above (recorded, not used for the headline comparison)
    glint  : B11 <= 0.10 instead of 0.03, and every band is glint-corrected by SWIR subtraction
             rho'(band) = rho(band) - rho(B11)   (spectrally flat glint assumption, as in common water processors)
  Primary = glint. NDCI/ratios are computed from corrected bands.

Time-match rule (predeclared):
  main      : each bin takes the scene with the smallest |acquisition - bin time| among the two same-survey 16TDQ scenes
              (2025-06-30 S2A, 2025-07-01 S2C) whose window is valid, and only if |lag| <= 24 h.
  single_0701 (sensitivity): every bin uses only the 2025-07-01 scene (one radiometrically consistent image), any lag.
  0701w24   (post-hoc compliance check): 07-01 scene only, restricted to |lag| <= 24 h.
  s0628     (24-72 h sensitivity tier, NOT the time-matched experiment): every bin uses only the clear 2025-06-28 scene.
Outputs: outputs/matched_bins.parquet, outputs/matchup_summary.json, figures/cloud_water_quality_check.png,
         figures/matched_footprint.png
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import distance_transform_edt

from p2_common import CAMPAIGN, DATA, FIG, MAX_LAG_H, OUT, TARGET, xc

MAIN = ["S2A_T16TDQ_20250630T164706_L2A", "S2C_T16TDQ_20250701T165332_L2A"]
SENS = ["S2C_T16TDQ_20250628T164829_L2A", "S2A_T16TDQ_20250703T165928_L2A"]
BAD_SCL = [0, 1, 3, 8, 9, 10, 11]
ADJ_M = 200.0
WIN = 2  # half-width in pixels -> 5 x 5 = 100 m
MIN_VALID = 13
FEATS = ["B02", "B03", "B04", "B05", "B06", "B07", "B8A", "B11"]


def load_scene(iid):
    with rasterio.open(DATA / f"{iid}_20m.tif") as src:
        A = src.read()
        names = list(src.descriptions)
        tf, t = src.transform, pd.Timestamp(src.tags()["datetime_utc"])
    S = {n: A[i] for i, n in enumerate(names)}
    return S, tf, t


VARIANTS = {"strict": dict(b11_max=0.03, glint=False), "glint": dict(b11_max=0.10, glint=True)}


def water_mask(S, b11_max=0.03, glint=False):
    finite = np.all([np.isfinite(S[b]) for b in FEATS], axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (S["B03"] - S["B11"]) / (S["B03"] + S["B11"])
    ok = finite & ~np.isin(S["SCL"], BAD_SCL) & (S["CLD"] <= 10) & (mndwi > 0) & (S["B11"] <= b11_max)
    dist = distance_transform_edt(ok) * 20.0  # metres to nearest failing pixel
    return ok & (dist >= ADJ_M), {"finite": finite, "scl_ok": ~np.isin(S["SCL"], BAD_SCL) & (S["CLD"] <= 10),
                                   "mndwi_water": mndwi > 0}


def sample(S, mask, tf, x, y, glint=False):
    col = np.floor((x - tf.c) / tf.a).astype(int)
    row = np.floor((y - tf.f) / tf.e).astype(int)
    H, W = mask.shape
    out = {b: np.full(len(x), np.nan) for b in FEATS}
    nvalid = np.zeros(len(x), int)
    for i, (r, c) in enumerate(zip(row, col)):
        if r - WIN < 0 or c - WIN < 0 or r + WIN >= H or c + WIN >= W:
            continue
        m = mask[r - WIN:r + WIN + 1, c - WIN:c + WIN + 1]
        nvalid[i] = m.sum()
        if nvalid[i] >= MIN_VALID:
            for b in FEATS:
                px = S[b][r - WIN:r + WIN + 1, c - WIN:c + WIN + 1][m]
                if glint and b != "B11":
                    px = px - S["B11"][r - WIN:r + WIN + 1, c - WIN:c + WIN + 1][m]
                out[b][i] = np.median(px)
    return out, nvalid


def main():
    obs, _ = xc.load_observations(CAMPAIGN, TARGET)
    obs["block"] = xc.make_blocks(obs, 5.0)
    x, y = obs.x.values, obs.y.values
    summary = {"mask": {"bad_scl": BAD_SCL, "cld_max_pct": 10, "mndwi_gt": 0, "variants": VARIANTS,
                        "adjacency_m": ADJ_M, "window_px": 2 * WIN + 1, "min_valid_px": MIN_VALID},
               "scenes": {}}
    M = obs.copy()
    scenes = {}
    for iid in MAIN + SENS:
        S, tf, t = load_scene(iid)
        lag_h = (t - obs.t_utc).dt.total_seconds().values / 3600.0  # + = image after boat
        scenes[iid] = dict(S=S, tf=tf, t=t, lag=lag_h, masks={}, f={}, nv={})
        for var, kw in VARIANTS.items():
            mask, _ = water_mask(S, **kw)
            f, nv = sample(S, mask, tf, x, y, glint=kw["glint"])
            ok = np.isfinite(f["B04"])
            scenes[iid]["masks"][var], scenes[iid]["f"][var], scenes[iid]["nv"][var] = mask, f, nv
            summary["scenes"].setdefault(iid, {"datetime_utc": str(t)})[var] = {
                "bins_valid": int(ok.sum()), "bins_total": int(len(obs)), "blocks_with_any_valid": int(obs.block[ok].nunique()),
                "water_px_valid_in_window": int(mask.sum()),
                "lag_h_range_valid": [float(lag_h[ok].min()), float(lag_h[ok].max())] if ok.any() else None}
            print(iid, var, "valid bins", ok.sum(), "/", len(obs), "blocks", obs.block[ok].nunique())

    def put(col_sfx, choice, lag):
        """choice: per-bin index into SCENE_LIST (-1 = unmatched)."""
        for b in FEATS:
            v = np.full(len(obs), np.nan)
            for k, iid in enumerate(SCENE_LIST):
                v[choice == k] = scenes[iid]["f"][var][b][choice == k]
            M[f"{b}_{col_sfx}"] = v
        M[f"scene_{col_sfx}"] = [SCENE_LIST[k] if k >= 0 else None for k in choice]
        M[f"lag_h_{col_sfx}"] = np.where(choice >= 0, lag, np.nan)
        M[f"matched_{col_sfx}"] = choice >= 0
        with np.errstate(invalid="ignore", divide="ignore"):
            M[f"NDCI_{col_sfx}"] = (M[f"B05_{col_sfx}"] - M[f"B04_{col_sfx}"]) / (M[f"B05_{col_sfx}"] + M[f"B04_{col_sfx}"])
            M[f"RG_{col_sfx}"] = M[f"B04_{col_sfx}"] / M[f"B03_{col_sfx}"]

    SCENE_LIST = MAIN + SENS
    for var in VARIANTS:
        # main rule: nearest valid same-survey scene with |lag| <= 24 h
        choice, best_lag = np.full(len(obs), -1), np.full(len(obs), np.inf)
        for k, iid in enumerate(MAIN):
            d = scenes[iid]
            okk = np.isfinite(d["f"][var]["B04"]) & (np.abs(d["lag"]) <= MAX_LAG_H) & (np.abs(d["lag"]) < np.abs(best_lag))
            choice[okk], best_lag[okk] = k, d["lag"][okk]
        put(f"{var}_main", choice, best_lag)
        for tag, iid in [("0701", MAIN[1]), ("0628", SENS[0])]:
            d = scenes[iid]
            okk = np.isfinite(d["f"][var]["B04"])
            put(f"{var}_{tag}", np.where(okk, SCENE_LIST.index(iid), -1), d["lag"])
        # post-hoc compliance check (added after results): 07-01 scene only, restricted to |lag| <= 24 h
        d = scenes[MAIN[1]]
        okk = np.isfinite(d["f"][var]["B04"]) & (np.abs(d["lag"]) <= MAX_LAG_H)
        put(f"{var}_0701w24", np.where(okk, SCENE_LIST.index(MAIN[1]), -1), d["lag"])
    M = M.rename(columns={"value": "chl_RFU"})
    M.to_parquet(OUT / "matched_bins.parquet")

    def blk(col):
        g = M.groupby("block")[f"matched_{col}"].mean()
        r = {"bins": int(M[f"matched_{col}"].sum()), "frac_bins": float(M[f"matched_{col}"].mean()),
             "blocks_any": int((g > 0).sum()), "blocks_ge50pct": int((g >= 0.5).sum()), "blocks_ge80pct": int((g >= 0.8).sum()),
             "abs_lag_h_median": float(M[f"lag_h_{col}"].abs().median()), "abs_lag_h_max": float(M[f"lag_h_{col}"].abs().max()),
             "seg32_bins_matched": int(M[M.block == 32][f"matched_{col}"].sum()), "seg32_bins": int((M.block == 32).sum())}
        if f"scene_{col}" in M:
            r["by_scene"] = M[f"scene_{col}"].value_counts().to_dict()
        s32 = M[(M.block == 32) & M[f"matched_{col}"]]
        r["seg32_lag_h"] = [float(s32[f"lag_h_{col}"].min()), float(s32[f"lag_h_{col}"].max())] if len(s32) else None
        return r
    summary["rules"] = {f"{v}_{r}": blk(f"{v}_{r}") for v in VARIANTS for r in ["main", "0701", "0628", "0701w24"]}
    summary["per_block_glint_main"] = M.groupby("block").agg(
        n=("x", "size"), matched=("matched_glint_main", "sum"), lag_h=("lag_h_glint_main", "median"),
        t_boat=("t_utc", "min")).reset_index().to_dict("records")
    (OUT / "matchup_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(pd.DataFrame(summary["rules"]).T.drop(columns=["by_scene"], errors="ignore").to_string())

    # ---- QC figure: true colour / SCL / NDCI / B04 on the primary (glint) mask for both main scenes
    fig, axs = plt.subplots(2, 4, figsize=(20, 12))
    for r, iid in enumerate(MAIN):
        d = scenes[iid]
        S, tf, mask = d["S"], d["tf"], d["masks"]["glint"]
        H, W = mask.shape
        ext = (tf.c, tf.c + W * tf.a, tf.f + H * tf.e, tf.f)
        with rasterio.open(DATA / f"{iid}_tci.tif") as src:
            tci = np.moveaxis(src.read(), 0, -1)
        axs[r, 0].imshow(np.clip(tci * 1.8, 0, 255).astype(np.uint8), extent=ext)
        axs[r, 0].set_title(f"{iid[:3]} {d['t']:%Y-%m-%d %H:%M} UTC  true colour (TCI x1.8)", fontsize=9)
        im = axs[r, 1].imshow(np.where(np.isin(S["SCL"], [3, 8, 9, 10]) | (S["CLD"] > 10), np.nan, S["B11"]),
                              extent=ext, cmap="turbo", vmin=0, vmax=0.12)
        axs[r, 1].set_title("B11 SWIR (glint/haze proxy); white = SCL cloud/shadow/cirrus or CLD>10", fontsize=9)
        fig.colorbar(im, ax=axs[r, 1], fraction=0.04)
        with np.errstate(invalid="ignore", divide="ignore"):
            b4, b5 = S["B04"] - S["B11"], S["B05"] - S["B11"]
            ndci = np.where(mask, (b5 - b4) / (b5 + b4), np.nan)
        im = axs[r, 2].imshow(ndci, extent=ext, cmap="viridis", vmin=-0.4, vmax=0.4)
        axs[r, 2].set_title("NDCI (glint-corrected) on final valid-water mask; grey = masked", fontsize=9)
        im2 = axs[r, 3].imshow(np.where(mask, b4, np.nan), extent=ext, cmap="magma", vmin=0, vmax=0.04)
        axs[r, 3].set_title("B04 red (glint-corrected BOA) on mask", fontsize=9)
        fig.colorbar(im, ax=axs[r, 2], fraction=0.04)
        fig.colorbar(im2, ax=axs[r, 3], fraction=0.04)
        on = M.scene_glint_main == iid
        for a in axs[r]:
            a.set_facecolor("0.8")
            a.plot(M.x, M.y, ",", color="k", alpha=0.4)
            a.scatter(M.x[on], M.y[on], s=1, color="cyan")
            a.set_xticks([]); a.set_yticks([])
    fig.suptitle("Scene QC (primary 'glint' mask). Cyan = bins matched to this scene under the main rule; black = full track",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "cloud_water_quality_check.png", dpi=80)
    plt.close(fig)

    fig, axs = plt.subplots(1, 3, figsize=(19, 8))
    for a, sfx, title in [(axs[0], "glint_main", "PRIMARY: nearest same-survey scene, |lag| <= 24 h"),
                          (axs[1], "strict_main", "predeclared strict mask (B11 <= 0.03), same rule"),
                          (axs[2], "glint_0628", "24-72 h tier: 2025-06-28 scene only")]:
        ok = M[f"matched_{sfx}"]
        a.scatter(M.x[~ok] / 1e3, M.y[~ok] / 1e3, s=2, c="k", marker="x", lw=0.4, label=f"unmatched ({(~ok).sum()})")
        sc = a.scatter(M.x[ok] / 1e3, M.y[ok] / 1e3, s=4, c=M[f"lag_h_{sfx}"][ok].abs(), cmap="plasma", vmin=0, vmax=75,
                       label=f"matched ({ok.sum()})")
        s32 = M.block == 32
        a.scatter(M.x[s32] / 1e3, M.y[s32] / 1e3, s=30, facecolors="none", edgecolors="lime", lw=0.8, label="segment 32")
        fig.colorbar(sc, ax=a, label="|image time - boat time| (h)", fraction=0.04)
        a.set_aspect("equal"); a.legend(fontsize=8); a.set_title(title, fontsize=10)
        a.set_xlabel("UTM 16N x (km)"); a.set_ylabel("y (km)")
    fig.tight_layout()
    fig.savefig(FIG / "matched_footprint.png", dpi=90)


if __name__ == "__main__":
    main()
