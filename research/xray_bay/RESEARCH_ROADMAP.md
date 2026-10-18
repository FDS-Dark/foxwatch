# Research roadmap

Ordered by expected value for X-Ray the Bay. "Verified" means the source was opened during this study (2026-10-17). "From brief" means the reference came from `docs/FoxWatch_WOW_Model_Research_Brief.md` and was not re-checked.

## 0. Immediate (days): harden the demo that already works

| # | Experiment | Why | Done when |
|---|---|---|---|
| 0a | **Same-day satellite covariate**: Sentinel-2 (NDCI, red/green) or Sentinel-3 OLCI CI from a clear pass on 2025-06-30 or 07-01, added as a feature to RF/GP | This is the only path to structure *between* tracks. It could catch filaments like segment 32. | It beats the coordinates-only models on **hard-scheme** MAE and within-segment r on the same 53 folds. First check cloud cover for those dates; if they are cloudy, use the nearest clear date and treat it as a time-lag test. |
| 0b | **Space-time GP**: add time to the kernel, or use separate length scales by time of day | June spans 2 days, and within-day plume movement is currently counted as spatial error | Lower hard-scheme MAE, and better ρ(|err|, SD) |
| 0c | **Non-stationary / heteroscedastic GP**: let the variance depend on distance to the mouth, or use a GP on residuals from the mouth-gradient model | The stationary GP over-smooths the mouth and does not localise its errors (ρ ≈ 0) | ρ(|err|, SD) > 0.3 with coverage kept |
| 0d | **GPU exact GP (GPyTorch)** on all bins, without the ≤800/1500 subsample | Removes subsampling noise; makes 0b and 0c cheap. An RTX 4080 SUPER is available locally. | Same CV and metrics |
| 0e | **Bathymetry covariate**: NOAA NCEI Great Lakes bathymetry (Lake Michigan) | Available everywhere, physically related to resuspension and turbidity, and known at unvisited points (unlike the boat's sonar depth, which is not) | Gain on turbidity in the hard scheme |
| 0f | **Better shoreline**: USGS NHD or OSM water polygons | The 1:10m mask is about 0.5–1 km off near shore and the river mouth | Visual check; fewer nearshore bins outside the mask |

## 1. Satellite ↔ field regression (weeks)

**Data:** FLAMe bins from all 8 campaigns, matched to Sentinel-2 L2A or ACOLITE-processed water reflectance within ±1–2 h or the same day. Sentinel-3 OLCI (300 m) is the coarser alternative.

**Labels:** chlorophyll and phycocyanin RFU, and turbidity FNU, from FLAMe. These are *field-sensor* labels, not lab values.

**Benefit:** about 450k georeferenced field rows (about 20k independent 100 m bins) is a large in-situ matchup set for one water body.

**Validation on Green Bay:**
- hold out whole **campaigns**, not points;
- report skill against an NDCI-only regression baseline;
- RFU-to-reflectance relationships may differ by season, so test transfer between campaigns.

**Caveat:** a 2026 USGS review of 122 Sentinel-2 chlorophyll studies finds most evidence is at early validation maturity (from brief): https://www.usgs.gov/publications/sentinel-2-chlorophyll-a-water-quality-monitoring-a-review-validation-evidence-and

## 2. GLORIA spectral models (weeks)

**Verified:** *GLORIA – a global dataset of remote sensing reflectance and water quality from inland and coastal waters*.

- Lehmann et al.; PANGAEA https://doi.org/10.1594/PANGAEA.948492; paper https://doi.org/10.1038/s41597-023-01973-y.
- **7,572** hyperspectral Rrs spectra (350–900 nm, 1 nm), from **450** water bodies and 53 institutions.
- Each spectrum has at least one of chlorophyll-a, TSS, CDOM absorption or Secchi depth. Licence CC-BY-4.0.

**Plan:**
1. Convolve the spectra with Sentinel-2 / OLCI spectral response functions.
2. Train chlorophyll-a and TSS regressors, holding out whole water bodies.
3. Apply them to atmospherically corrected Green Bay scenes.
4. Validate against FLAMe on the same dates.

**Labels are lab chlorophyll-a in µg/L, which is not EXO2 RFU.** Validation can only be by rank or correlation, unless a local RFU-to-lab calibration exists (`FLAMe_samples.csv` has `lab_id` keys for joining lab results, but those results are not in this release).

## 3. Western Lake Erie transfer (weeks–months)

**Verified:** NOAA GLERL / CIGLR, *Physical, chemical, and biological water quality monitoring data to support detection of HABs in western Lake Erie, since 2012*, https://doi.org/10.25921/11da-3x54 (NCEI).

- Weekly May–October cruises with **extracted chlorophyll-a, extracted phycocyanin, particulate and dissolved microcystin**, nutrients, TSS, turbidity and CDOM.
- Moored buoys since 2014 with sonde chlorophyll and phycocyanin. CSV and shapefile.

**Use:** pretrain satellite → chlorophyll/phycocyanin models on Erie, then evaluate on Green Bay FLAMe matchups in three variants: Erie-only, Green Bay-only, and Erie + Green Bay calibration.

**Risk:** Green Bay's CDOM and optical water type differ from Erie's. A Green Bay comparison found river discharge explains little of peak bloom intensity (R² 0.14, vs 0.75 for the Maumee River in Erie) (from brief; Wynne et al. 2022, https://repository.library.noaa.gov/view/noaa/49251). Expect domain shift, and test across lakes explicitly.

## 4. Earth-observation foundation models (months; deferred)

**Clay v1.5 (verified):**
- Checkpoint at `https://huggingface.co/made-with-clay/Clay/resolve/main/v1.5/clay-v1.5.ckpt`.
- Apache-2.0 for code and weights.
- Inputs include Sentinel-2 L2A (10 bands), Landsat, Sentinel-1, MODIS and NAIP. Outputs 1024-d embeddings.
- **No water-quality task is published.**

**Experiment:** frozen embeddings of chips around FLAMe bins, plus a small regressor, compared against an NDCI/band-ratio regressor on held-out campaigns. Run this only after item 1 establishes a reflectance baseline.

**Prithvi-EO-2.0 and TerraMind** (from brief): HLS-based, 30 m. Band and scale compatibility must be checked. No water head should be assumed.

**Guardrail:** an embedding model is **not** a validated HAB detector. Any output must be validated against field labels, as in items 1–3.

## 5. Active sampling, done properly (months)

The current result: in replay, GP-guided suggestions beat random choice (29 % vs 22 % mean error reduction). **A model-free distance rule did as well.**

Next steps:
- **Sequential replay:** reveal the survey in time order, and at each step recommend the next area. Compare against the route actually taken and against random choice.
- Add **travel cost** (distance from the boat's current position).
- Use a **non-stationary** uncertainty (item 0c) so that "where the model is wrong" differs from "where there is no data". Only then can a model-based rule beat the distance heuristic.

Prior work (from brief):
- Frontiers in Marine Science 2021, https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2021.689489/full
- Advanced Intelligent Systems 2024, local GPs for water monitoring, https://doi.org/10.1002/aisy.202300850

## Things *not* to do

- Do not merge campaigns months apart into one map.
- Do not use random point splits to report skill: they inflate R² from about 0.85 to 0.98.
- Do not use boat-measured covariates (sonar depth, temperature, conductivity) as inputs at unvisited points. They are not available there.
- Do not convert EXO2 RFU to "µg/L chlorophyll" or to "bloom" or "toxin" labels.

## References

- Data: https://doi.org/10.5066/P1XHRFKZ (verified)
- FLAMe method: Crawford et al. 2015, https://doi.org/10.1021/es504773x ; Loken et al. 2019, https://doi.org/10.1029/2019JG005186 (from release metadata)
- Spatial cross-validation: Roberts et al. 2017, *Ecography*, https://doi.org/10.1111/ecog.02881 (from brief)
- NOAA NCCOS Green Bay cyanobacteria imagery: https://coastalscience.noaa.gov/science-areas/habs/hab-monitoring-system/cyanobacteria-algal-bloom-from-satellite-in-green-bay-and-lake-winnebago-wi/ (from brief)
- NDCI: https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/ndci/ (from brief)
- Oblique geographic coordinates as RF features: Møller et al. 2020, *SOIL*, https://doi.org/10.5194/soil-6-269-2020 (method reference for the rotated-coordinate features)
