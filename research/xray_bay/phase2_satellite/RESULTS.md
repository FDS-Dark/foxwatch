# Phase 2 results: does Sentinel-2 reflectance add information beyond spatial interpolation?

**Target:** `chl_RFU_exo_tau`, in-vivo chlorophyll **fluorescence** from the EXO2 sensor, in RFU. It is not chlorophyll-a concentration and not a bloom or toxin indicator.

**Survey:** USGS FLAMe `GreenBay_2025_Jun`, 2025-06-30 14:25 to 2025-07-01 18:36 UTC, the same 2,497 × 100 m bins as Phase 1.

**Evaluation:** Phase 1 leave-one-5 km-segment-out.
- **hard scheme (primary):** the segment, 1 km of same-track buffer, and every bin within 1.5 km of the segment are all removed from training;
- **standard scheme:** only the segment and the 1 km same-track buffer are removed.

Within a rule, every model is scored on **identical matched bins and identical folds**. Numbers from different rules come from different subsets and must not be compared with each other or with Phase 1's full-survey 0.615 RFU.

Reproduce: `scripts/01…07`. All numbers below come from `outputs/metrics.json`, `outputs/satellite_model_comparison.csv` and `outputs/paired_folds.csv`.

## 1. Gates

| Gate | Outcome |
|---|---|
| G0 discovery | **Pass.** One 16TDQ pass on each survey day: 06-30 16:51 UTC (S2A) and 07-01 17:01 UTC (S2C). See SCENE_AUDIT.md. |
| G1 pixel validity | **Pass, with a documented deviation.** 06-30 is mostly cirrus. 07-01 is clear but glint-affected: the predeclared B11 ≤ 0.03 screen kept only 77 bins. SWIR-subtraction glint correction restored 1,692. |
| G2 paired matchup | **Pass.** Primary rule: 1,630 bins (65%), median lag 2.9 h; 48 of 53 hard folds eligible. |
| G3 independent gain | **Mixed.** See below. |

## 2. Models

| Name | Inputs |
|---|---|
| `nn`, `idw` | Phase 1 interpolators |
| `rf_xy` | Phase 1 RF on coordinates (x, y + 7 rotations). **Fair location-only control** |
| `gp_xy` | Phase 1 GP (Matérn 3/2 + noise), coordinates |
| `rf_xysat` | `rf_xy` features + B03, B04, B05, NDCI (glint-corrected) |
| `rf_xysat_ext` | + B02, B06, B07, B8A, red/green ratio |
| `rf_sat`, `lin_sat` | satellite features only (RF / linear) |
| `gp_resid` | linear satellite trend + GP on coordinates for the residual ("regression kriging") |

## 3. Primary result: rule `glint_main` (predeclared), hard scheme, 48 folds, 1,625 bins

| Model | MAE (RFU) | RMSE | R² | Within-segment median r |
|---|---:|---:|---:|---:|
| nn | 0.814 | 1.589 | 0.57 | 0.40 |
| idw | 0.725 | 1.477 | 0.63 | 0.35 |
| **rf_xy (best location-only)** | **0.630** | 1.289 | 0.71 | 0.51 |
| gp_xy | 0.702 | 1.432 | 0.65 | **0.60** |
| rf_sat | 0.685 | 1.305 | 0.71 | 0.33 |
| **rf_xysat** | **0.609** | 1.216 | 0.75 | 0.48 |
| rf_xysat_ext | 0.614 | 1.232 | 0.74 | 0.34 |
| gp_resid | 0.692 | 1.294 | 0.71 | 0.37 |

**`rf_xysat` vs `rf_xy`:**
- MAE change −3.4%, fold-bootstrap 95% CI **−7.9% to +3.1%**;
- 25 folds improved, 23 worse; Wilcoxon p = 0.21 (descriptive only);
- within-segment r drops slightly (0.51 → 0.48).

**This misses the predeclared >10% bar. H1 is not supported under the primary rule.**

In the standard scheme the change is −3.1% (CI −7.1% to +2.2%).

## 4. Sensitivity: single, clear same-survey image (07-01 S2C)

The primary rule mixes two images. The scene-consistency check (`outputs/scene_consistency.json`, `figures/scene_consistency.png`) shows that is harmful:

- On the 268 bins that both scenes see, the two disagree: Spearman ρ between scenes is 0.36 for NDCI and 0.51 for B05.
- Fluorescence rank-correlates with B05 at **0.85** on 07-01-matched bins, but only **0.63** on 06-30-matched bins, which sit near cirrus.

`glint_0701w24` uses the 07-01 scene only, keeps bins with |lag| ≤ 24 h, and puts the remaining bins at 1.6 h before to 23.9 h after the boat. **It is a post-hoc variant**: it was added after the primary result was known.

Hard scheme, 44 folds, 1,490 bins:

| Model | MAE (RFU) | R² | Within-segment r |
|---|---:|---:|---:|
| idw | 0.720 | 0.64 | 0.33 |
| rf_xy | 0.678 | 0.68 | 0.29 |
| **gp_xy (best location-only)** | **0.668** | 0.69 | **0.67** |
| rf_sat (satellite only) | **0.552** | 0.77 | 0.30 |
| **rf_xysat** | **0.588** | 0.76 | 0.50 |
| gp_resid | 0.594 | 0.72 | 0.26 |

| Comparison (hard) | Pooled MAE change | Fold-bootstrap 95% CI | Folds improved |
|---|---:|---|---:|
| rf_xysat vs rf_xy | **−13.3%** | **−18.5% to −7.1%** | 29 / 44 |
| rf_xysat vs gp_xy (best location-only) | −12.1% | −32.5% to +12.4% | 28 / 44 |
| rf_xysat vs idw | −18.4% | −35.8% to −0.3% | 29 / 44 |
| rf_sat vs gp_xy | −17.3% | −41.9% to +23.0% | 23 / 44 |

The other single-scene rules behave the same way:
- **`glint_0701`** (any lag, 50 folds): −13.6% vs rf_xy and −12.0% vs gp_xy.
- **`glint_0628`**, a clear image **46–74 h before** the survey (38 folds): −14.3% vs rf_xy and −10.3% vs gp_xy.

**A 2–3-day-old image helps as much as the same-day one.** The useful information is a plume geometry that persists for days, not something only a time-matched image can see.

**Strict-mask variant** (`strict_main`, 16 folds of low-fluorescence outer-bay water): −3.1%, CI −6.5% to +1.6%. Little to gain where there is little structure.

## 5. Segment 32 (predefined plume-filament diagnostic)

Segment 32 is 46 bins measured 2025-07-01 from 14:06 UTC along the SE shore. The 07-01 image was taken 2.7–2.9 h after the boat passed. Observed fluorescence averages 7.7 RFU and peaks at 15.3 RFU.

| Model (hard scheme) | Primary rule: MAE / bias (RFU) | Single-scene ≤24 h: MAE / bias | Primary: r along segment |
|---|---|---|---:|
| idw | 5.23 / −5.23 | 4.75 / −4.75 | 0.81 |
| rf_xy | 4.18 / −4.18 | 3.97 / −3.97 | 0.79 |
| gp_xy | 4.73 / −4.73 | 4.27 / −4.27 | 0.84 |
| rf_xysat | 3.86 / −3.86 | 3.54 / −3.54 | 0.75 |
| rf_sat | 1.90 / −1.32 | **1.30 / −0.27** | 0.69 |
| lin_sat | **1.61 / −1.04** | 1.44 / −0.84 | **0.91** |
| **gp_resid** | **1.62 / −1.08** | 1.45 / −0.85 | **0.91** |

**What this table shows:**
- **Location-only models flatten the filament.** Every one under-predicts by about 4–5 RFU, reproducing the Phase 1 failure.
- **Satellite-driven models largely recover it.** Wherever the satellite sets the level (`gp_resid`, `lin_sat`, `rf_sat`), segment 32 error falls by **61–67%** and the bias falls from about −4 to about −1 RFU. `gp_resid` peaks at 15.7 RFU against an observed 15.3.
- **The pooled winner does not fix it.** `rf_xysat` improves segment 32 by only 8%: with coordinates available, the trees mostly split on location and barely use the satellite features.

**Intervals on segment 32 (primary rule):**
- `gp_xy` 80% intervals contain only 13% of observations; this is worse than Phase 1's 35%, on a different fold subset.
- `gp_resid` 80% intervals contain 62%, and 95% intervals contain 93%.

See `figures/segment32_satellite_reveal.png`. The B05 panel shows a bright red-edge band hugging the SE shore exactly where the filament was measured.

## 6. Failure cases

- **The model that fixes segment 32 breaks elsewhere.** Under the primary rule, `gp_resid` is worse than `gp_xy` in 30 of 48 hard folds and worse than `rf_xy` in 33. Its large failures are the river-mouth segments 27–31, 49 and 51 (e.g. segment 51: +2.6 RFU vs rf_xy).
  - Most of those bins use the 07-01 scene alone.
  - At the mouth, B05 brightness keeps rising (sediment, shallow bottom, shore adjacency) while fluorescence does not. A single linear trend fitted to the whole bay overshoots there.
  - Segment 31 also mixes 10 bins from 06-30 with 23 from 07-01, which produces the 1–8 RFU swings visible in `figures/reveal_seg31.png`.
- **Typical fold, segment 17 (outer bay):** every model is within 0.1 RFU, so the satellite adds nothing (`figures/reveal_seg17.png`).
- **Largest improvement, segment 52 (mouth, 16 of 33 bins matched):** `gp_resid` 0.74 vs `rf_xy` 3.47 RFU (`figures/reveal_seg52.png`).
- **Satellite-only models degrade within-segment shape on average** (r 0.26–0.36 vs 0.60–0.67 for gp_xy). The improvement is mostly in getting each segment's *level* right, not its fine structure. **H2 is supported for segment 32, not in general.**

## 7. What the satellite signal is

- **B05 and B04 carry the signal; NDCI does not.** On the 07-01 matched bins, B05 has Spearman ρ = 0.83 with fluorescence and B04 0.79; NDCI only 0.25.
- **The signal is turbid plume brightness.** In this survey fluorescence and turbidity co-vary at ρ = 0.91, and B05 tracks turbidity at ρ = 0.82. B05 is most plausibly detecting the **turbid, productive Fox River plume as a whole**, not a chlorophyll-specific spectral signature. The satellite helps because, here, chlorophyll fluorescence follows the plume. **That relationship is not guaranteed in other seasons or in bloom conditions that do not follow the plume.**
- **Not water-leaving reflectance.** Reflectance is Sen2Cor land-oriented BOA with a flat-glint SWIR subtraction.

## 8. Uncertainty (H3)

| Rule (hard) | Model | 80% coverage | 95% coverage | Spearman(|err|, SD) |
|---|---|---:|---:|---:|
| glint_main | gp_xy | 0.89 | 0.93 | +0.06 |
| glint_main | gp_resid | 0.87 | 0.95 | **−0.16** |
| glint_0701w24 | gp_xy | 0.90 | 0.94 | +0.05 |
| glint_0701w24 | gp_resid | 0.88 | 0.96 | **−0.19** |

**H3 is not supported.** Average coverage is acceptable, slightly too wide at 80%. But the satellite-informed GP's SD does not rank errors at all, and is weakly anti-correlated with them: its largest errors come from the trend term, which carries no uncertainty. **No uncertainty layer from this work should be presented as validated.**

## 9. Limitations and leakage review

- **Post-hoc choices.** The glint mask was chosen after the pixel audit, though before any target comparison. The single-scene ≤24 h variant was added after the primary result was known. The predeclared primary result is the −3.4% one.
- **One survey, two images, one season.** Fold-bootstrap intervals treat folds as independent, but neighbouring segments share plume structure.
- **Matched subset under-represents the plume.** The shore and cloud buffers drop many high-fluorescence mouth bins; segments 41–52 are only partly matched.
- **No leakage paths found.**
  - Folds are Phase 1's, computed on the full bin set.
  - Satellite pixels at held-out locations are independent observations.
  - Held-out fluorescence never enters features, scaling or masks.
  - The linear trend's standardisation uses training folds only.
  - The mask, window and eligibility thresholds do not use target values.
- **Atmospheric correction.** Sen2Cor plus flat-glint subtraction is crude. Residual glint is a smooth cross-bay field that coordinates can partly absorb.

## 10. Answer

**Does satellite reflectance add genuine predictive information beyond spatial interpolation, particularly for the plume filament?**

**Yes, but only with a single clean image, and not robustly enough for a headline claim.**

- **Segment 32:** satellite-driven models cut the Phase 1 plume-filament error by about two-thirds (4.2 → 1.3–1.6 RFU). The B05 image shows the filament the boat never crossed in training.
- **Single clean scene, hard holdout:** adding the satellite to RF improves pooled MAE by 12–14% over the best location-only model on identical bins. The interval excludes zero against the matched RF control, but not against the GP.
- **Predeclared primary (two mixed scenes):** −3.4%, CI includes zero.
- **Persistence, not time-matching:** a 2–3-day-old image works as well as the same-day one, so the evidence is for persistent plume structure, not for time-matched chlorophyll detection.
- **No single model wins everywhere:** the model that fixes segment 32 fails badly at the river mouth.

Decision: see [DECISION.md](DECISION.md).
