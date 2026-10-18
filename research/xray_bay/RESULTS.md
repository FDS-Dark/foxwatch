# X-Ray the Bay — feasibility results

**Recommendation: CONDITIONAL GO.**

The data support a defensible hide → predict → reveal demonstration on the **30 June – 1 July 2025 cross-bay FLAMe survey of Green Bay** (`GreenBay_2025_Jun`). The prediction is chlorophyll-a fluorescence (RFU), restricted to water within 3 km of a measurement. The demonstration is **not** supported in three cases:

- the 7–10 July 2025 campaign: in its Green Bay portion, a 1-D distance-from-river-mouth curve does as well as any spatial model;
- the open bay more than 3 km from the track;
- any claim of lab chlorophyll-a, toxin or bloom status.

Every number below is produced by `scripts/03_experiment.py`, `03b_mouth_baseline.py`, `04_demo.py` and `05_report.py`. They are in `outputs/metrics.json`, `outputs/metrics_summary.json`, `outputs/results_table.csv`, `outputs/mouth_baseline.json` and `outputs/demo_summary.json`.

---

## 1. Hypothesis

Within a single survey, a measured water-quality variable can be estimated at **unvisited locations in the same water body** with useful accuracy. "Useful" means a clear improvement over a constant, and competitive with or better than interpolation. The test is to hold out whole survey segments rather than random points, and the estimate should come with an uncertainty that is honest on held-out data.

## 2. Task definition

| | |
|---|---|
| Target (primary) | `chl_RFU_exo_tau`: in-vivo chlorophyll-a fluorescence from the YSI EXO2, corrected for hydraulic lag and sensor response time, in **RFU**. This is **not** extracted chlorophyll-a in µg/L. |
| Secondary targets | `bga_RFU_exo_tau` (phycocyanin fluorescence, RFU), `turb_FNU_tau` (turbidity, FNU), `specCond_tau` (specific conductance, µS/cm) |
| Domain | Green Bay water: points inside the Natural Earth Lake Michigan polygon, buffered by 1 km. This drops the Fox River corridor. |
| Unit of observation | Median over a 100 m along-track bin. 40,776 one-second rows become 2,497 bins for the primary configuration. |
| Inputs at the query point | Location only: UTM 16N x/y, plus rotated copies of the coordinates for the tree models. No target-derived features. No covariates measured on the boat. |
| Temporal assumption | One campaign is treated as one snapshot. `GreenBay_2025_Jun` spans 2025-06-30 14:25 to 2025-07-01 18:36 UTC. Changes within those two days are folded into the error. |
| CRS | Modelling in EPSG:32616. GeoJSON exports in WGS84 lon/lat. |

## 3. Evaluation protocol

- **Holdout unit:** contiguous 5 km along-track segments. Every segment is held out once, giving 53 folds for June, 35–36 for April and 14 for July.
- **Standard scheme:** the segment plus **1 km of same-track neighbours on each side** are removed from training.
- **Hard scheme:** additionally removes every training bin within **1.5 km** of the held-out segment, such as crossing transects and return legs. This mimics reconstructing a gap with no nearby evidence.
- **Leakage control (invalid, shown only for contrast):** a random 20 % of bins held out, with their neighbours left in training.
- **Fit only on training bins:**
  - IDW and nearest-neighbour use only the training bins.
  - The models' log transform uses a fixed offset (`log(v+1)`), so no held-out statistic is used.
  - GP kernel hyperparameters are re-fitted in every fold.
- **Metrics:**
  - MAE, RMSE, R² and bias in target units, pooled across folds.
  - MAE per fold.
  - **Within-segment median r**: correlation between prediction and truth along each hidden segment, i.e. whether the shape is right, not just the level.
  - Interval coverage for the GP and for random-forest tree spread.

### Methods

| Name | What it is |
|---|---|
| mean | Training mean (sanity floor). |
| nn | Nearest training bin. |
| idw | Inverse-distance weighting, power 2, 12 neighbours. Raw units, fixed parameters. |
| **mouth** | **Skeptic's baseline**: monotone (isotonic) fit of the target against distance to the Fox River mouth. Tests whether a "spatial" model only learns the plume gradient. |
| rf | Random forest, 300 trees, on x/y plus 6 rotated coordinate axes, fitted in log space. |
| hgb | Histogram gradient boosting, same features. |
| gp | Exact Gaussian process with a Matérn-3/2 + white-noise kernel, fitted in standardised log space on a random subsample of ≤800 training bins. Hyperparameters are fitted per fold. |

## 4. Results

### 4.1 Primary: `GreenBay_2025_Jun`, chlorophyll fluorescence (RFU)

The target across bins has mean 1.94 RFU (5th–95th percentile about 0.55–8.3).

| Scheme | Folds / points | mean | NN | IDW | **mouth** | RF | HGB | GP |
|---|---|---|---|---|---|---|---|---|
| standard: MAE (RFU) | 53 / 2,497 | 1.94 | 0.51 | 0.50 | 0.98 | **0.44** | 0.46 | 0.46 |
| standard: R² | | −0.05 | 0.85 | 0.84 | 0.52 | 0.88 | **0.89** | 0.88 |
| hard: MAE (RFU) | 53 / 2,497 | 1.99 | 0.83 | 0.76 | 1.25 | 0.65 | 0.68 | **0.62** |
| hard: R² | | −0.11 | 0.61 | 0.65 | 0.28 | 0.75 | 0.74 | **0.81** |
| within-segment median r (standard / hard) | | | 0.50 / 0.23 | 0.47 / 0.32 | | 0.57 / 0.35 | 0.52 / 0.31 | **0.61 / 0.59** |
| **random split (LEAKY)**: R² | | | 0.98 | 0.98 | | 0.99 | 0.99 | |

What this table shows:

- **Spatial reconstruction is real.** Every spatial method roughly halves the error of the plume-gradient-only baseline: MAE 0.44–0.50 against 0.98 RFU in the standard scheme, and 0.62–0.76 against 1.25 in the hard scheme.
- **ML over interpolation is a modest gain when evidence is close and a real gain when it is far.** In the standard scheme the best model beats IDW by 13 % (MAE 0.44 vs 0.50). In the hard scheme the GP beats IDW by **20 %** (0.62 vs 0.76) and keeps within-segment shape (r 0.59 vs 0.32).
- **Random splits would have overstated skill.** The leaky control gives R² 0.98–0.99 against 0.84–0.88 under honest spatial holdout.

### 4.2 All configurations: MAE, with the best non-trivial value in bold

| Config | Scheme | NN | IDW | mouth | RF | HGB | GP | Best vs IDW |
|---|---|---|---|---|---|---|---|---|
| Jun 2025 chl (RFU) | std | 0.506 | 0.504 | 0.977 | **0.439** | 0.459 | 0.458 | −13 % |
| | hard | 0.827 | 0.764 | 1.247 | 0.654 | 0.683 | **0.615** | −20 % |
| Jun 2025 phycocyanin (RFU) | std | 0.127 | 0.128 | 0.239 | **0.110** | 0.114 | 0.122 | −14 % |
| | hard | 0.193 | 0.178 | 0.283 | 0.148 | **0.143** | 0.152 | −20 % |
| Jun 2025 turbidity (FNU) | std | 0.876 | 0.855 | 1.318 | **0.752** | 0.779 | 0.836 | −12 % |
| | hard | 1.090 | 1.031 | 1.444 | **0.879** | 0.900 | 1.005 | −15 % |
| Jun 2025 sp. cond. (µS/cm) | std | 5.93 | 6.03 | 12.55 | **5.07** | 5.07 | 5.96 | −16 % |
| | hard | 8.12 | 7.75 | 15.91 | **6.46** | 6.62 | 10.55 | −17 % |
| Apr 2025 chl (RFU) | std | 0.859 | **0.849** | 1.395 | 0.908 | 1.027 | 1.055 | IDW best |
| | hard | **0.982** | 1.064 | 1.495 | 1.109 | 1.171 | 1.539 | NN best |
| Apr 2025 turbidity (FNU) | std | 1.227 | **1.216** | 1.923 | 1.267 | 1.331 | 1.667 | IDW best |
| | hard | 1.551 | 1.469 | 2.009 | **1.397** | 1.613 | 1.894 | −5 % |
| Jul 2025 chl (RFU), mouth loops | std | 0.701 | 0.707 | 0.608 | **0.519** | 0.576 | 0.683 | −27 %, but only −15 % vs mouth |
| | hard | 0.966 | 0.891 | **0.636** | 0.717 | 0.689 | 0.840 | **mouth baseline best** |
| Jul 2025 turbidity (FNU), mouth loops | std | 3.88 | 3.86 | 3.30 | **2.77** | 2.82 | 3.61 | −28 % |
| | hard | 4.83 | 4.72 | 4.53 | **3.05** | 3.56 | 4.81 | −35 % |

R² for every cell is in `outputs/results_table.csv` and in `figures/cv_skill_standard.png` and `figures/cv_skill_hard.png`. The NN bar for July chlorophyll in the hard scheme (R² −0.69) is clipped at −0.3 in the figure.

Patterns:

1. **June 2025 (cross-bay zig-zag, 2 days):** all four targets reconstruct well. Pooled R² is 0.77–0.93 in the standard scheme and 0.65–0.90 in the hard scheme. A trained model beats IDW by 12–20 % MAE in every case.
2. **April 2025 (same design, cold water):** IDW or NN is as good as or better than every trained model. **The ML advantage does not replicate.** The GP is the worst spatial method here (hard-scheme R² 0.59 for chlorophyll), which points to a kernel or stationarity problem in that campaign.
3. **July 2025 (one day of near-mouth loops):** reconstruction is weak (R² 0.10–0.49 for chlorophyll). For chlorophyll the 1-D mouth-distance curve matches or beats the spatial models. For turbidity, RF does beat the mouth baseline. This geometry does **not** support a credible 2-D chlorophyll map.

### 4.3 Uncertainty (Experiment C)

Coverage is the share of held-out bins whose true value falls inside the nominal interval. Spearman ρ is the rank correlation between |error| and the uncertainty estimate.

| Config | Scheme | GP 80 % | GP 95 % | ρ(|err|, GP SD) | RF tree-spread 80 % | ρ(|err|, distance to nearest obs) |
|---|---|---|---|---|---|---|
| Jun chl | std | 0.84 | 0.91 | 0.15 | 0.59 | −0.10 |
| Jun chl | hard | 0.92 | 0.97 | 0.03 | 0.65 | −0.14 |
| Jun bga | std / hard | 0.82 / 0.90 | 0.90 / 0.96 | 0.05 / 0.02 | 0.58 / 0.57 | −0.03 / −0.13 |
| Jun turb | std / hard | 0.80 / 0.86 | 0.88 / 0.94 | 0.10 / 0.16 | 0.67 / 0.71 | −0.11 / −0.19 |
| Jun spec. cond. | std / hard | 0.83 / 0.81 | 0.92 / 0.89 | −0.04 / −0.09 | 0.68 / 0.71 | −0.03 / −0.07 |
| Apr chl | std / hard | 0.88 / 0.87 | 0.94 / 0.97 | 0.10 / 0.04 | 0.64 / 0.58 | −0.12 / −0.08 |
| Jul chl | std / hard | 0.76 / 0.83 | 0.89 / 0.98 | 0.44 / 0.30 | 0.58 / 0.59 | 0.07 / −0.15 |

Findings:

- **On average, GP intervals are approximately calibrated on held-out segments.** The 80 % intervals cover 76–92 % of bins and the 95 % intervals cover 88–98 %. They tend to be slightly too wide in the hard scheme and slightly too narrow in the standard scheme for some targets.
- **The intervals do not point to where the errors are.** ρ between |error| and GP SD is close to zero in Green Bay. The kernel is stationary, so the GP SD is essentially a function of distance to the track (see `figures/sampling_suggestions_*.png`). Distance to the nearest observation is *slightly negatively* related to error. The largest errors occur in the densely sampled, highly variable plume near the river mouth, not in sparse open water.
- **Random-forest tree spread is not an uncertainty.** Its "80 %" intervals cover only 56–71 %.
- **How to label the layer:** the GP SD can be described as a **calibrated-on-average predictive interval, verified by held-out coverage for this campaign**. It must not be described as "the model knows where it's wrong". In the UI, call it *"evidence coverage / expected error band"*.

### 4.4 Demonstration segments

The two demo segments were chosen by fixed rules before results were seen, not picked for good performance:

| Segment | Rule | Hidden bins | GP MAE | IDW MAE | GP 80 % interval hit rate |
|---|---|---|---|---|---|
| 23 "central" | segment nearest the centroid of all bins (mid-bay crossing) | 47 | 0.28 RFU | **0.06 RFU** | 100 % |
| 32 "hardest" | largest within-segment SD of the target | 46 | **3.79 RFU** | 4.44 RFU | 35 % |

- **Segment 23:** the true values are flat at about 1.0 RFU. IDW, which copies the transects at both ends, is nearly exact. The GP is smoothed upward by about 0.3 RFU by the higher plume values further south, and its interval is very wide. *A simple method wins here, and the demo should say so.*
- **Segment 32:** a nearshore plume filament along the east shore, 8–15 RFU. **Every method under-predicts it by about 4 RFU**, because no training data show values that high nearby. This is the honest failure case, and it is the kind of place a boat should go next.

Figures:

- `figures/xray_demo_GreenBay_2025_Jun__chl_RFU_exo_tau_seg23.png` and `..._seg32.png`: the four states. A observed; B hidden; C and C′ reconstruction and uncertainty with no-estimate masking; D and D′ the reveal, with errors and interval hits/misses.
- `figures/sampling_suggestions_GreenBay_2025_Jun__chl_RFU_exo_tau.png`: the reconstruction from all bins, plus 5 suggested next measurements.
- `figures/cv_skill_standard.png` and `figures/cv_skill_hard.png`: skill for every configuration against the leaky random split.
- `figures/audit_*.png`: the raw tracks for all 8 campaigns.

### 4.5 Active sampling (optional extension), evaluated by replay

For each of the 53 June chlorophyll segments:

1. Hide the segment.
2. Choose **one** bin on it to "measure", by a given rule.
3. Re-fit the GP with its hyperparameters frozen.
4. Measure the MAE on the rest of the segment.

| Rule | Mean MAE after 1 reveal (before: 0.457 RFU) | Mean relative reduction | Segments where it beats random |
|---|---|---|---|
| random (mean of 20 draws) | 0.347 | 22 % | n/a |
| **max GP SD** | **0.317** | **29 %** | 36 / 53 |
| GP integrated variance reduction (IVR) | 0.333 | 28 % | 36 / 53 |
| farthest from existing evidence (no model) | 0.321 | 28 % | 38 / 53 |

- **Targeted sampling beats random choice by about 7 percentage points**, and wins in about 70 % of segments.
- **The model-free rule "go farthest from existing data" does as well as the GP-based rules.** This follows from §4.3: the GP SD is essentially a function of distance.
- **Claim we can make:** uncertainty-guided suggestions beat random sampling in replay.
- **Claim we cannot make:** that the model finds better locations than a distance heuristic, or that the suggestions are optimal.

The five suggested next measurements are greedy IVR picks with 3 km spacing. They lie inside the supported domain, at least 500 m from the coarse shoreline and 2.2–3.0 km from the nearest bin: `outputs/geo/sampling_candidates_GreenBay_2025_Jun__chl_RFU_exo_tau.geojson`.

| Rank | Lat | Lon | Predicted chl (RFU) | Distance to nearest obs |
|---|---|---|---|---|
| 1 | 44.8088 | −87.7739 | 1.14 | 2.96 km |
| 2 | 44.7165 | −87.7790 | 1.13 | 2.81 km |
| 3 | 44.6642 | −87.8445 | 1.32 | 2.59 km |
| 4 | 44.7567 | −87.8174 | 1.15 | 2.43 km |
| 5 | 44.9243 | −87.6551 | 1.34 | 2.16 km |

## 5. Failures, limitations and leakage risks

1. **Within-day dynamics are folded into "spatial" error.** The June campaign spans 2 days. A segment sampled on 1 July is predicted from transects sampled on 30 June. This makes the test harder, not easier, but some "spatial" error is really temporal.
2. **Remaining spatial leakage.** The standard scheme still lets crossing transects within 1.5 km inform the hidden segment. The hard scheme removes them, so treat the hard numbers as the headline for "reconstructing gaps".
3. **Hyperparameters were chosen once, not tuned per fold.** These are IDW p/k, RF/HGB settings, the GP kernel family, the 5 km block, the 100 m bin and the 3 km support radius. They were not tuned on the test folds, but they were set after looking at the June tracks. The GP kernel hyperparameters *are* re-fitted per fold.
4. **Stationary GP.** One length scale (about 2.5–3 km) for both the sharp river plume and the smooth open bay. This causes over-smoothing at segment 23 and miscalibration at segment 32, and explains why uncertainty does not localise errors.
5. **The ML advantage does not replicate in April 2025.**
6. **July 2025 (the period FoxWatch cares about) does not support 2-D reconstruction of chlorophyll**, beyond a river-mouth gradient.
7. **Fluorescence is not a concentration.** RFU is affected by non-photochemical quenching (time of day), temperature and community composition. Nothing here detects toxins or confirms a bloom.
8. **Coarse coastline (1:10m).** The water mask and the "no estimate" mask are approximate within about 0.5–1 km of shore and at the river mouth.
9. **Pooled R² rewards getting the level right.** Within-segment shape correlation is moderate (median r about 0.5–0.6 at best). The models reconstruct *regional* patterns well and *fine structure* only partly.

## 6. Is it scientifically credible?

Yes, with the scope above. The pieces that make it credible:

- whole-segment holdouts, plus a buffered "hard" variant;
- three naive baselines, including the plume-gradient skeptic's baseline;
- a leaky-split control that shows the inflation it avoids;
- interval coverage measured on held-out data;
- demo segments picked by pre-stated rules, one of which is a failure the demo shows rather than hides.

## 7. What is ready to integrate into FoxWatch

All files are in `outputs/geo/`:

| File | Format | Contents |
|---|---|---|
| `observations_GreenBay_2025_Jun__chl_RFU_exo_tau.geojson` | GeoJSON, WGS84 | 2,497 100 m bins with UTC time, value, units, segment id, provenance |
| `demo_holdout_..._seg23.geojson` and `..._seg32.geojson` | GeoJSON | hidden bins with truth, prediction, error, lower80/upper80, model version |
| `reconstruction_..._seg23.tif` and `..._seg32.tif` | GeoTIFF, EPSG:32616, 250 m | bands: mean, sd_model_space, lower80, upper80. NaN means no estimate. Tags carry variable, units, campaign, time span, model, provenance and caveats. |
| `reconstruction_..._full.tif` | GeoTIFF | the same, reconstructed from all bins |
| `sampling_candidates_....geojson` | GeoJSON | 5 suggested points with predicted value, SD, distance to evidence, and a method label |

Machine-readable metrics are in `outputs/metrics.json` (full), `outputs/metrics_summary.json` (compact) and `outputs/results_table.csv`.

**Recommended demo script:**

1. Show the June 30 – July 1 2025 track.
2. Hide segment 32 (the plume filament).
3. Show the GP reconstruction with the 3 km mask and the IDW comparison.
4. Reveal: "all methods under-predicted this filament by about 4 RFU; our 80 % band caught 35 % of it."
5. Show the overall scoreboard: across 53 hidden segments, MAE 0.46 RFU in the standard scheme and 0.62 in the hard scheme, against IDW at 0.50 and 0.76.
6. Show the sampling suggestion, which beat random choice in replay.

Segment 23 is the "a simple method wins too" moment.

## 8. Single most valuable next experiment

**Add a time-matched, wall-to-wall covariate and re-run the same hard-scheme test.** The best candidate is Sentinel-2 or Sentinel-3 reflectance (NDCI and red/green indices) from a cloud-free pass on 30 June or 1 July 2025.

Today, every method only interpolates between tracks, so it cannot see the filament in segment 32. A same-day satellite field is the only input that can, in principle, place structure in unsampled water. The test is whether "GP/RF + satellite covariate" beats "GP/RF on coordinates" on the *same* held-out segments, using the hard-scheme MAE and the within-segment r.

If it does, X-Ray the Bay can extend beyond 3 km of the track. If it doesn't, the 3 km mask stays.
