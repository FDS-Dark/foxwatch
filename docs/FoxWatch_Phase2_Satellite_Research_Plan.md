# FoxWatch / X-Ray the Bay — Research Phase 2
## Can satellite imagery recover spatial water-quality structure missed by vessel measurements?

**Status:** Proposed experiment · **Scope:** Standalone ML research, not FoxWatch platform implementation · **Reference:** X-Ray the Bay Phase 1 feasibility report

## 1. Decision to make

**Question:** Does time-matched, spatially continuous Sentinel-2 reflectance improve prediction of in-vivo chlorophyll-a **fluorescence (RFU)** at withheld survey locations, beyond what location-only spatial methods already achieve?

Phase 1 measured the following on the **GreenBay_2025_Jun** campaign (2025-06-30 14:25 to 2025-07-01 18:36 UTC):

| Measure | Existing result |
|---|---:|
| Survey rows / 100-m bins | 40,776 / 2,497 |
| Evaluation | 53 contiguous 5-km withheld segments; standard and buffered hard schemes |
| Hard-holdout Gaussian process (GP) MAE / R² | **0.615 RFU / 0.81** |
| Hard-holdout inverse-distance weighting (IDW) MAE | **0.764 RFU** |
| Segment 32 (hard-to-predict plume filament) GP MAE | **3.79 RFU** |
| Segment 32 80% interval coverage | **35%** |

**These are reported results from the prior local experiment, not re-run by this document.**

### Hypotheses

- **H1:** Satellite reflectance/features improve held-out segment MAE compared with an identically evaluated **coordinate-only model on the same valid satellite-matched bins**.
- **H2:** Satellite features help reconstruct fine structure along segments, measured by within-segment correlation and targeted diagnostics for segment 32.
- **H3 (optional):** Satellite-informed models yield better error localization or predictive interval behavior. Previous GP intervals had roughly appropriate *overall* coverage but weak correlation with local error. Do not assume H3 is true.

**Non-goals:** Detecting toxins or harmful blooms; converting fluorescence RFU to chlorophyll-a concentration; operational forecasting; deploying services; training a U-Net or foundation model; unmasked estimates for the entire bay.

## 2. Research inputs

**Already available locally (expected):**

- Original FLAMe survey and metadata; target `chl_RFU_exo_tau` (YSI EXO2 lag/response-corrected in-vivo fluorescence in RFU).
- `scripts/03_experiment.py`, `03b_mouth_baseline.py`, `04_demo.py`, `05_report.py` and the associated preprocessing scripts.
- `outputs/metrics.json`, `outputs/metrics_summary.json`, `outputs/results_table.csv`, segment metadata, observations GeoJSON and existing holdout outputs.
- Geographic modeling CRS **EPSG:32616**; exported GeoJSON WGS84; previous **3-km observation-support** mask.

**New input to audit:** Sentinel-2 Level-2A observations near 30 June / 1 July 2025, ideally same-day. Research these in order:

1. **Element 84 Earth Search STAC** — <https://earth-search.aws.element84.com/v1>; query `sentinel-2-c1-l2a` (and inspect `sentinel-2-l2a` as an alternate collection) for an AOI derived from the actual survey tracks. Retrieve Cloud-Optimized GeoTIFF band assets rather than rendered JPEG/PNG imagery.
2. **Copernicus Data Space Sentinel Hub** — <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html> if Earth Search lacks a needed scene/asset. Requires appropriate credentials.
3. Only **if Sentinel-2 cannot support the experiment**, audit Landsat 8/9 or Sentinel-3 as explicitly different-resolution follow-ups. Do not silently substitute them or claim they can resolve the same plume detail.

Minimum reflectance bands: **B03 (green), B04 (red), B05 (red edge)** and QA/SCL; optional B02, B06, B08, B8A, B11. NDCI = `(B05-B04)/(B05+B04)` is a *satellite spectral index*, not the boat fluorescence label. Red-edge B05 is native 20 m: use explicit/common resolution and record resampling choices. Apply asset-provided scale and offset rather than treating raw integer DN as reflectance.

## 3. Go/no-go gates

| Gate | Action | Pass criteria and implications |
|---|---|---|
| **G0: Satellite discovery** | Query STAC over survey footprint and **2025-06-29 through 2025-07-02**; record every acquisition time, footprint and scene ID. Expand to ±3 days only as a sensitivity/exploratory analysis. | At least one spatially overlapping image, with plausible temporal proximity. No assumption that a same-day acquisition exists. |
| **G1: Pixel validity** | Inspect actual water-area pixels, cloud/shadow/cirrus, sunglint, shoreline adjacency and no-data. Scene-wide cloud percent is insufficient. | Enough trustworthy matched pixels on both training and withheld sections. Report counts by fold and time lag before fitting models. |
| **G2: Paired experiment** | Extract reflectance/features at same locations as 100-m bins, assigning imagery by a **predeclared time-matching rule**. | Both location-only and satellite-enhanced models evaluated on identical matched bins and identical holdout folds. |
| **G3: Independent gain** | Run existing hard spatial scheme; compare improvements in MAE, within-segment r, and selected segment diagnostics. | Only claim added satellite value if the gain survives spatial holdout, fair matched-sample comparison and basic sensitivity checks. |

**Practical data sufficiency rule:** Target at least 25 of 53 usable held-out folds for any broad generalization claim. With 10–24 usable folds, label the result **limited/conditional evidence**; with fewer than 10, prefer a data-audit and visual case study over headline model scores. This is a project decision threshold, not a scientific standard.

**Time-match tiers:** Main experiment: closest valid acquisition **within 24 h of the corresponding boat sample**, recording exact lag; do not assert an acquisition is available. Optional sensitivity: 24–72 h; clearly separate from main results. If no adequate imagery within 24 h, report **NO-GO for the time-matched claim** rather than redefining the target silently. Don't combine acquisitions across days into an undocumented mosaic.

## 4. Controlled data and model comparison

### Data preparation

1. Reuse the same **100-m bins**, survey segments and underlying geographic footprint. For each bin, save satellite item ID, acquisition time, boat measurement time, signed/absolute time lag, band reflectance, masks and valid-pixel coverage.
2. Use a carefully constrained local pixel aggregation rule (e.g., a small surrounding water-only footprint) established before looking at target values. Avoid using pixels contaminated by land or cloud; use a 20-m-common-resolution feature grid for red-edge features.
3. Apply clouds, cloud shadows, cirrus, no-data, shoreline and suspicious reflectance masks. Inspect a true-color and band/QA panel to ensure turbid water is not falsely removed as land or cloud. Do not infer accuracy from SCL alone.
4. Compute a minimal feature set first: B03, B04, B05 and NDCI; optionally a red/green index and B06, with a record of feature choices. Normalize using **training-fold statistics only** where relevant.
5. Label extracted covariates as satellite reflectance, **not observed fluorescence**. A pixel at a withheld location may be used as an input because it is an independent, wall-to-wall observation; field sensor values from the hidden segment must remain excluded.

### Models (in this sequence)

| Model | Purpose |
|---|---|
| IDW on the matched subset | Non-ML reference (unchanged by satellite) |
| Coordinate-only RF and/or GP | **Fair same-subset control** |
| Coordinates + B03/B04/B05/NDCI, RF | Fastest credible satellite-enhanced baseline |
| Coordinates + satellite covariates, GP or GP residual correction | More complex candidate **only if time and valid coverage permit** |
| Satellite-only regression (optional) | Tests whether spectral information independently explains variation |

**Evaluation is identical to Phase 1 wherever possible:** 5-km contiguous holdout sections, 1-km same-track buffer, and **hard** holdout excluding training bins within 1.5 km of withheld section, including other transects. Preserve folds and original baseline hyperparameters, or document any unavoidable deviations. **Never use random split as the primary result.**

Crucial distinction: if quality filtering reduces the dataset, **rerun the coordinate-only baselines on exactly that subset**. The Phase 1 whole-survey MAE (0.615 RFU) is historical context, **not a fair direct comparator** to a new smaller matched subset.

### Metrics and interpretation

Primary: pooled **MAE in RFU**, across eligible **hard** spatial folds, and change vs matched-subset coordinate-only GP/RF and IDW. Secondary: RMSE, R², per-fold MAE/paired changes, within-segment correlation (shape), valid-fold count, image time lag and matched-point coverage. Evaluate segment 32 as a **predefined diagnostic** rather than selecting the one best-looking segment. Also show one typical segment and one failure.

If producing intervals, report 80%/95% coverage and whether uncertainty ranks actual errors better than Phase 1. Do **not** equate tree spread or a distant-from-track map with calibrated uncertainty.

Suggested **research-success bar**: >10% relative MAE gain vs the **best location-only method on the matched subset** under hard holdout, without substantially worsening individual folds or within-segment shape, and preferably improved segment 32. This is a demanding demo go/no-go heuristic, **not** a claim of statistical significance. A smaller consistent gain may still be publishable as a useful finding. If it fails, report the negative result.

## 5. Time-boxed execution

| Time | Research deliverable | Exit decision |
|---|---|---|
| 0–25 min | STAC inventory + candidate scene footprints/times | Do valid near-date images exist? |
| 25–55 min | Quality-masked scene, matched survey bins, QC plot and coverage table | Is evaluation adequately populated? |
| 55–100 min | RF location-only vs RF+satellite, IDW matched control; representative folds then all feasible hard folds | Is there promising incremental skill? |
| 100–130 min | GP follow-up if justified, segment 32 image/reveal, error & uncertainty audit | Does the WOW story hold up? |
| Last 20 min | Reproducibility, report, exported artifacts, go/no-go | Deliver an actual decision |

This is a **~2.5-hour cap**; stop early if the satellite gate fails. Preserve all prior Phase 1 outputs. The platform team can continue independently while this experiment runs.

## 6. Outputs and handoff

```
research/xray_bay/phase2_satellite/
  README.md
  SCENE_AUDIT.md
  MATCHUP_AUDIT.md
  RESULTS.md
  DECISION.md
  scripts/
  outputs/
    scene_inventory.csv
    matched_bins.parquet
    satellite_model_comparison.csv
    metrics.json
    selected_scene_ids.json
  figures/
    acquisition_timeline.png
    cloud_water_quality_check.png
    matched_footprint.png
    hard_holdout_comparison.png
    segment32_satellite_reveal.png
  exports/                   # only if successful
    satellite_covariates.tif
    predicted_chl_rfu.tif
    prediction_support_mask.tif
    segment32_predictions.geojson
```

The filenames above are **expected outputs**, not claims that they already exist. Each raster needs CRS, bounds, resolution, UTC acquisition metadata, valid-pixel mask, variable **RFU**, scene IDs and model lineage. Do not put any credentials into the repository.

### Report one of three outcomes

- **GO:** Adequate time-matched coverage plus repeatable spatial-holdout gains over same-subset baselines, with clear limitations.
- **CONDITIONAL GO:** Some scene coverage/gain, but limited geography, temporal mismatch, poor transfer, or weak interval validation.
- **NO-GO:** Imagery unavailable/unusable or additional spectral features do not help. Existing coordinate-only X-Ray the Bay remains the platform's validated option.

## 7. Scientific limitations to preserve

- The measured target is **in-vivo fluorescence RFU**, not laboratory chlorophyll concentration or toxin concentration.
- Sentinel-2 L2A is an **optical land-oriented surface-reflectance product**; over turbid coastal water, atmospheric/adjacency corrections and shallow/shoreline effects require special caution. Treat extracted reflectance as an experimental predictor, not automatically a water-leaving reflectance product.
- The June survey spans **two dates**, so even same-calendar-day passes can have hours of mismatch; quantify it.
- The Phase 1 distance-to-observation uncertainty indicator did **not** reliably identify the largest errors; don't present the satellite-enhanced uncertainty layer as validated without tests.
- Demonstrating retrospective information gain within a single survey is **not** prospective forecasting or generalization to a new season.

## 8. Useful source documentation

- Element 84 Earth Search STAC: <https://earth-search.aws.element84.com/v1>
- Earth Search collections, COG assets, scale/offset caveat: <https://github.com/Element84/earth-search>
- Sentinel-2 L2A access: <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html>
- S2L2A examples including multi-band GeoTIFF and cloud/SCL: <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S2L2A.html>
- USGS 2026 review of Sentinel-2 aquatic chlorophyll validation: <https://www.usgs.gov/publications/sentinel-2-chlorophyll-a-water-quality-monitoring-a-review-validation-evidence-and>
