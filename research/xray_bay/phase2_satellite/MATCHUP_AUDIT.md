# Matchup audit (gate G2)

Regenerate with `scripts/03_masks_matchup.py`. Outputs:
- per-bin table: [`outputs/matched_bins.parquet`](outputs/matched_bins.parquet);
- summary: [`outputs/matchup_summary.json`](outputs/matchup_summary.json);
- maps: [`figures/matched_footprint.png`](figures/matched_footprint.png).

## What is matched

The bins are the **same 2,497 × 100 m bins** as Phase 1: `xray_common.load_observations("GreenBay_2025_Jun", "chl_RFU_exo_tau")`. `04_experiment.py` asserts that positions and values are identical.

Each bin gets:
- the median of the valid 20 m water pixels in a **5 × 5 pixel (100 m) window** centred on the bin (at least 13 of 25 pixels must be valid);
- for each band: B02, B03, B04, B05, B06, B07, B8A, B11;
- NDCI = (B05 − B04)/(B05 + B04) and red/green = B04/B03, computed from glint-corrected bands.

These are **satellite reflectance features, not observed fluorescence**. Using the pixel at a held-out location is legitimate, because the image is an independent, wall-to-wall observation. Held-out boat values are never used.

Per-bin columns:
- scene ID;
- acquisition time vs. boat time, as a signed lag (`lag_h_*`, positive = image after the boat);
- number of valid pixels;
- matched flag.

## Time-matching rules (fixed before modelling)

| Rule | Definition | Bins matched | Segments with any / ≥50% / ≥80% matched | Median / max abs lag | Segment 32 |
|---|---|---:|---|---|---|
| **`glint_main` (PRIMARY)** | nearest valid same-survey scene (06-30 or 07-01), lag ≤ 24 h | **1,630 (65%)** | 50 / 35 / 23 | **2.9 h** / 23.9 h | 45/46 bins (40 from 07-01 at +2.7 to +2.9 h, 5 from 06-30 at −21.3 h) |
| `glint_0701` | 07-01 scene only, any lag | 1,692 (68%) | 53 / 37 / 22 | 19.6 h / 26.4 h | 40/46 |
| `glint_0701w24` | 07-01 scene only, lag ≤ 24 h. **Post-hoc** compliance check, added after the results above | 1,496 (60%) | 46 / 32 / 22 | 19.2 h / 23.9 h | 40/46 |
| `glint_0628` | 06-28 scene only (**24–72 h tier, not time-matched**) | 1,700 (68%) | 38 / 37 / 33 | 69.8 h / 73.7 h | 46/46 |
| `strict_main` | predeclared strict mask, same rule as primary | 445 (18%) | 28 / 7 / 5 | 3.3 h / 23.6 h | 3/46 |

The primary rule draws 1,281 bins from the 07-01 scene and 349 from the 06-30 scene. **Because 06-30 is cirrus-covered over the middle bay, segments 7–29 (all measured on 30 June) mostly fall back to the 07-01 image, 19–24 h after the boat passed.** About half of the primary set is therefore a same-hour match, and half is a next-day match. `glint_0701` uses a single image, so it shows whether mixing two scenes' radiometry matters.

## What is missing

- **Segments 4, 5 and 6 (outer bay, 30 June) have no valid pixels in either same-survey scene.** Segments 1 and 45 have ≤ 3 bins.
- Matched coverage is lowest in segments 41–52 (lower bay, mouth). These have 2–35 of 45–50 bins, because of the 200 m shore and cumulus-adjacency buffer and small clouds near the mouth on 07-01. **This is exactly where fluorescence is highest** (segments 47–52 average 5–10 RFU). The matched subset therefore under-represents the plume, so the scores below are **not** comparable to Phase 1's full-survey numbers.
- In the hard scheme, a fold is **eligible** if it keeps at least 10 matched test bins and at least 100 matched training bins. Fold counts by rule and scheme are in RESULTS.md.

## Leakage controls

- Folds are computed on the full 2,497 bins with Phase 1's `fold_split`, then intersected with the matched subset. The 1 km along-track buffer and 1.5 km spatial exclusion are therefore exactly Phase 1's, even where satellite gaps would otherwise shift a buffer.
- Satellite features are standardised (for the linear trend inside `gp_resid` only) with **training-fold** statistics. Tree models need no scaling.
- The log(v + 1) offset is a fixed constant.
- The mask, window size, minimum pixel count, time-matching rule, feature list and fold-eligibility thresholds were all set before any model was fitted. The one deviation (the glint mask) was decided from pixel and B11 diagnostics alone; see SCENE_AUDIT.md.
