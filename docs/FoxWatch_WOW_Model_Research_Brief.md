# FoxWatch — Model Research & the WOW-Factor Decision

**Research brief | October 17, 2026 | For HackGB implementation planning**

> **Decision:** Make FoxWatch an **evidence-aware spatial reconstruction and sampling assistant**, not another bloom-heatmap app. Build **X-Ray the Bay:** ingest a real FLAMe survey, estimate a chosen observed water-quality variable between surveyed tracks, show where the model **doesn't know**, hide one survey segment, and reveal it to assess the prediction. If spatial coverage is inadequate, reduce scope to measured transects, anomaly explanations and evidence gaps. Do not imply water-quality conditions in unsampled areas were actually measured.

## What research changes the product decision

1. **A large local, dense, georeferenced dataset exists.** The USGS FLAMe release contains **455,102 observations** and **239 associated sample/field records** across **eight campaigns in 2023–2025** along Lake Winnebago, the Fox River and Green Bay, recording up to **82 variables** depending on instrument/campaign. July 2025 is one candidate campaign. Variables include algal fluorescence/taxa-related optical signals, turbidity, nitrate, conductivity and more. **Not all 455k records are July 2025, within Green Bay, or independent.** We have verified metadata, **not loaded/inspected the raw CSV**. [USGS release](https://www.usgs.gov/data/high-spatial-resolution-sensor-based-surface-water-quality-data-along-lake-winnebago-fox-river) · [DOI](https://doi.org/10.5066/P1XHRFKZ).
2. **Satellite bloom mapping already exists for Green Bay.** NOAA NCCOS has an operational Green Bay/Lake Winnebago Sentinel-3 cyanobacteria visualization and downloadable imagery. To be novel, FoxWatch needs **explanation, field-sensor integration, uncertainty and action**, not another colored overlay. [NOAA product](https://coastalscience.noaa.gov/science-areas/habs/hab-monitoring-system/cyanobacteria-algal-bloom-from-satellite-in-green-bay-and-lake-winnebago-wi/).
3. **Lake Erie is not Green Bay.** A Green Bay comparison study found river discharge alone correlated relatively weakly with peak Green Bay bloom intensity (reported R² 0.14), compared with Lake Erie's Maumee River (R² 0.75), and indicated a role for colored dissolved organic matter and other factors. A Lake Erie model requires external-domain validation before making Green Bay claims. [Wynne et al. 2022, NOAA-hosted PDF](https://repository.library.noaa.gov/view/noaa/49251/noaa_49251_DS1.pdf).
4. **Satellite chlorophyll estimation is not solved.** A 2026 USGS review of **122** Sentinel-2 chlorophyll studies finds most evidence is still at early validation maturity; pairing in-situ samples with appropriately processed reflectance and honest validation is the hard part. [USGS review](https://www.usgs.gov/publications/sentinel-2-chlorophyll-a-water-quality-monitoring-a-review-validation-evidence-and).

## The recommended WOW demo: “X-Ray the Bay”

### The 90-second magic trick

**Show:** actual FLAMe research-vessel path with measured **turbidity** or a verified algae-related sensor variable. Identify a geographically separate set of observations to withhold. **Predict:** produce a spatially limited reconstruction between neighboring tracks, with missing-data zones and an uncertainty/evidence-coverage layer. **Reveal:** overlay the hidden observations and report held-out MAE (and RMSE if useful). **Act:** show the next location a hypothetical sampling team should investigate because the evidence is weak or the estimate is uncertain. **Explain:** Gemini links the original measurements and states why this location was recommended; no invented values.

What this demonstrates that NOAA's static maps don't: *measured evidence → model estimate → test against unseen evidence → actionable evidence-gap recommendation*.

**This must be conditional.** Boat routes may be single narrow corridors or separated in time. A visually continuous 2D Green Bay forecast would be scientifically indefensible if there are no neighboring same-day transects. Reject 2D extrapolation when coverage fails. Constrain models to an explicitly supported sampling footprint; depict unsampled zones as **no estimate**.

### Targets, prioritized by actual 2025 coverage

1. **Turbidity**: likely an interpretable observed target and easier to explain to judges. Confirm July availability and units first.
2. **Total algal fluorescence**: usable as an instrument signal, not equal to lab-extracted chlorophyll-a and not toxicity.
3. **Blue-green-algae / cyanobacteria-associated fluorescence or fluoroprobe group estimate**: more interesting, **only if** present and quality-controlled in the chosen FLAMe campaign. Do not equate to actual toxin hazard or confirmed species.
4. **Discrete nutrient or lab samples**: supplemental validation, not dense pixel labels. Exact counts/locations and depth need inspection.

### Minimum realistic modeling ladder

| Level | Method | What is trained? | Expected build effort after clean data | Judgment |
|---|---|---|---|---|
| A — baseline | Nearest-neighbor / inverse distance weighting (IDW) | Nothing; transparent interpolation | ~1–2 h | **Mandatory**; compare everything with it. |
| B — practical trained model | Random Forest or HistGradientBoosting regression (location, time, nearby measurement context; spectral covariates **only** if truly time-matched) | Local target regression on verified FLAMe observations | ~2–5 h | **Best actual trained model for the hackathon**, if data geometry supports holdout testing. |
| C — uncertainty-first spatial model | Local Gaussian process / kriging on spatially representative, downsampled subset | Spatial structure + estimated variance | ~3–6 h, depending on coverage, variogram and sample size | Good for visualization and uncertainty; *not* on all 455k points with exact GP. |
| D — spectrally learned | Gradient boosting or compact MLP trained on GLORIA in-situ spectra paired to measured Chl-a / TSS | Aquatic optical water-quality regression | Many hours + preprocessing/validation; probably **post-hackathon** | Scientifically better motivated than training a generic pixel segmenter without labels. |
| E — weak-label segmentation | U-Net on Sentinel-2 using coarse Sentinel-3 CI products as weak labels | Coarse proxy/weak label agreement | Days, not hours, unless whole pipeline is already prepared | Not a hackathon blocker; never call output validated 10-m cyanobacteria truth. |
| F — foundation model research | Clay v1.5 or other EO backbones for embeddings/finetuning | Satellite representation and downstream probe | Additional data engineering & GPU time | **Deferred:** embeddings alone do not detect blooms. |

Effort figures are **engineering planning estimates**, not source-derived benchmarks.

### Honest uncertainty and evaluation

- Test on **entire held-out transect/route segment** (and preferably another campaign for generalization), not random sensor rows. Dense boat samples are autocorrelated and random splits create misleadingly good test scores. [Roberts et al. 2017](https://doi.org/10.1111/ecog.02881).
- Measure **MAE, RMSE**, spatial error distribution and data coverage for the chosen actual target units. Compare against a **nearest-neighbor/IDW** baseline; don't display an unsupported accuracy percentage.
- Use a calibrated prediction interval only after testing interval coverage on separate spatial holdouts. Otherwise call the layer **ensemble disagreement / evidence coverage**, not calibrated confidence.
- Water masks and reachable/sampled regions must be explicit. If output is 100-m pixels, call that the **model-grid size**, not inherent data resolution or 100-m accuracy.
- Avoid interpolating across days without a validated temporal model. Never merge May, June and July 2025 as simultaneous observations.
- Build an **interactive reveal experiment** only if withheld measurements were excluded from all training/tuning/normalization operations.
- For active sampling, recommend a **candidate measurement point**, not a navigational route or a claim of actual downstream pollution source.

## Secondary WOW direction: “Algae or sediment?”

**Research hypothesis:** Some unusual water-color patterns are associated with sediment/turbidity, some with algal biomass, and some are optically ambiguous. FoxWatch can show NDCI/red-edge chlorophyll-related index, a red/green turbidity-related index, and actual nearby FLAMe/USGS fluorescence and turbidity records to compare hypotheses.

**Good demo**: two selected water patches that appear unusual, one with field evidence of turbidity and another with algal-related fluorescence. The panel says **"Evidence supports elevated turbidity"** / **"Algal signal elevated; toxin status unknown"** / **"Insufficient matched observations"**, not “AI confirmed bloom.”

A truly learned classifier is conditional on coincident labels from the same satellite observation date/area. **If the satellite matchup is bad, keep this feature an evidence comparison, not an asserted model classification.**

Reference NDCI: (Sentinel-2 B05 - B04) / (B05 + B04), a relative red-edge pigment proxy for productive waters, **not** an automatic µg/L concentration. [Sentinel Hub NDCI](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/ndci/). Sentinel-2 B05 and B06 are nominally 20-m bands; mixed-resampling and optical limitations must be considered. [ESA/GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/sentinel-2).

## Third WOW direction: active sampling / "What would you measure next?"

Suggest the next sample based on a map of model uncertainty, **only inside the region for which recommendations can be meaningfully made**, ideally accounting for travel effort. This is a genuine research direction: field reconstruction with GP uncertainty and optimized sample locations has precedent in the aquatic monitoring literature. See [Frontiers 2021: in-situ+remote sensing, optimal sampling](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2021.689489/full) and [Wiley 2024: local GPs for water monitoring](https://doi.org/10.1002/aisy.202300850).

**Most compelling validation:** replay the actual survey sequentially, deliberately exposing only the first N measurements; choose the next recommended unsampled area and compare its usefulness with a random sampling baseline based on withheld historical values. If that's too much, display a transparent heuristic (large predicted gradient + sparse nearby evidence) and label it as **suggested, not optimized**.

## Longer-term model research: real aquatic labels

### GLORIA (highest-priority scientific training source)

The **GLORIA** dataset has **7,572 actual in-situ hyperspectral water reflectance records**, collected in ~450 distinct water bodies, with at least one paired chlorophyll-a/TSS/CDOM/Secchi measurement. Spectra cover 350–900 nm. This is far more physically relevant for water-quality learning than faux segmentation masks or training on another model's predictions. [GLORIA paper](https://doi.org/10.1038/s41597-023-01973-y) · [Data DOI](https://doi.org/10.1594/PANGAEA.948492).

Suggested research: convolve in-situ spectra with **Sentinel-2 spectral response functions**, train separate Chl-a and TSS regressors (only on valid labeled subsets), hold out complete water bodies, test on Green Bay *independent measured records* after atmospheric/aquatic-reflectance matching and (if necessary) sparse site-specific calibration. The workflow exists in recent studies, including [2026 physics-guided inversion from GLORIA](https://doi.org/10.1016/j.ecoinf.2026.103611). **Do not treat in-situ Rrs, satellite L2A surface reflectance, and chlorophyll fluorescence as interchangeable.**

### NOAA GLERL / CIGLR western Lake Erie (regional transfer)

NOAA provides measured extracted chlorophyll-a, phycocyanin, microcystin and nutrients with repeated western Lake Erie sampling from 2012 onward; station and data archives are documented. [GLERL weekly data](https://www.glerl.noaa.gov/res/HABs_and_Hypoxia/wle-weekly-current/) · [NOAA archival collection](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.nodc%3AGLERL-CIGLR-HAB-LakeErie-water-qual).

Purpose: create time-matched satellite/field observation pairs for **measured chlorophyll-a regression** or carefully specified bloom-intensity proxies; compare **trained on Erie only**, **trained on Green Bay limited samples**, and **Erie pretrain + Green Bay calibration**. Keep testing independent by **year, station and/or water body**. Green Bay's CDOM dynamics imply domain shift and may require optical-water-type calibration [Wynne et al. 2022](https://repository.library.noaa.gov/view/noaa/49251).

### EO foundation models and few-shot alternatives

- **Clay v1.5**: published pretrained checkpoints and documentation for Sentinel-2 bands/embeddings; its general Earth observation representation is not a trained HAB detector. Suitable experiment: frozen embeddings + a small field-measurement regressor, versus a simpler optical-index baseline. [Clay quickstart](https://clay-foundation.github.io/model/getting-started/quickstart.html), [GitHub](https://github.com/Clay-foundation/model).
- **Prithvi-EO-2.0**: NASA/IBM pretraining on Harmonized Landsat–Sentinel multispectral data with temporal context at **30 m**, so spectral-band/scale compatibility to Sentinel-2 L2A must be checked. No available water-specific supervised head should be assumed. [Repository](https://github.com/NASA-IMPACT/Prithvi-EO-2.0).
- **TerraMind**: pretrained EO foundation model with TerraTorch examples; powerful but not an out-of-box HAB model. [IBM repository](https://github.com/IBM/terramind).
- **Few-shot Chl-a ResNet transfer**: [2026 study](https://www.sciencedirect.com/science/article/pii/S1569843226002104), [author code](https://github.com/zsxdapple/A-few-shot-ResNet-transfer-learning-method-for-Chla-retrieval); repository visibly offers a training script, **but no obvious ready-to-run model checkpoint file in its root listing**, so treat as reproduction research rather than instant drop-in inference.
- **Utah Lake 6-year product**: primarily satellite-derived or interpolated targets; useful for pretraining/prototypes, **not independent ground truth for your satellite model**. [Zenodo](https://zenodo.org/records/15677449).

## Proposed model evaluation program (post-hackathon)

1. **Local reconstruction:** same-day FLAMe sample → spatially held-out transects → MAE/RMSE, map/evidence coverage, uncertainty calibration, nearest/IDW comparison.
2. **Spectral regression:** GLORIA supervised models for *lab-measured* Chl-a and TSS → water-body-out holdout → compare against NDCI, B5/B4 and other physical baselines → limited local calibration with proper same-day samples.
3. **Cross-lake transfer:** western Lake Erie → Green Bay with aquatic optical correction, study how performance varies with turbidity/CDOM. Compare to local-only calibration and no-calibration baseline.
4. **Weak-label mapping:** NOAA/EPA Sentinel-3 CI as **coarse spatial supervisory signal**, never independent fine-pixel reference; evaluate on independently measured or sampled Green Bay observations.
5. **Time forecasting:** only after several seasons of independently verified events and appropriate negative observations. Use chronological leakage-free splits and compare to persistence/seasonality. No 48-hour alert claims on scarce or opportunistically reported labels.

## Next two hours: go/no-go tests

**First 30–45 min** — Obtain and inspect `FLAMe_data.csv`, `FLAMe_data_dictionary.csv`, survey location map. Determine exact July 2025 campaign dates, bounding coordinates, chosen target's units, quality flags and whether useful same-day nearby transects exist. **If no data download or usable geometry, do not build interpolation.**

**Next 45–75 min** — Plot **raw points on map** with color by chosen field measurement. Create an IDW/nearest-neighbor baseline **within justified extent** and a clearly marked spatial holdout; display quantitative holdout error. No training necessary yet.

**Next 60–120 min** — If evaluation is credible, train small RF/gradient-boosting model, compare with baseline, add hide/reveal toggle and gap/uncertainty overlay; otherwise concentrate on measured track and evidence visualization.

**Mandatory submission fallback:** real station charts + real FLAMe point map + sourced historical timeline + inspectable image proxy. An honest working system beats a visually compelling but invalid 'whole-bay prediction.'

### Judge demonstration, 3 minutes

- **0:00–0:20** — 'Boats can only sample part of Green Bay. How do we know where to look next?' Show real sensor tracks.
- **0:20–1:10** — Hide a preselected survey segment; predict inside defensible coverage; display map and uncertainty/coverage layer.
- **1:10–1:45** — Reveal held-out observations; present actual error vs baseline, mention any mismatch without excuses.
- **1:45–2:20** — Ask FoxWatch to pick a follow-up measurement candidate; explain why it is informative (not a guaranteed bloom location).
- **2:20–2:50** — Click a point and show original source/time/variable alongside satellite and weather context; Gemini explains the uncertainty.
- **2:50–3:00** — 'We don't just color the water. We show what we know, test what we predict, and tell you where evidence is missing.'

## Caveats and hard restrictions

- **Data-access status:** publisher pages/repositories were verified during this research, but **no FLAMe raw CSV or training run was executed here**. Model practicality is therefore conditional on the raw data/schema and local results.
- **Do not claim** 455k independent examples, a confirmed July 2025 bloom, 10-m true biomass maps, toxin detection, real-time monitoring, validated runoff scenarios, or calibrated model confidence without appropriate field/lab support.
- **Do not fake tests:** if you visualize a synthetic example or replay data, label it. Synthetic data cannot be used as evidence of field accuracy.
- **Avoid overpromising** on the exact feature being ready overnight: if model cannot beat simple interpolation in spatial holdout, show the baseline and spend time on evidence-driven UX and honest scientific framing.

## Core references (primary sources)

1. [USGS FLAMe data release (Oct 8, 2026)](https://www.usgs.gov/data/high-spatial-resolution-sensor-based-surface-water-quality-data-along-lake-winnebago-fox-river)
2. [NOAA NCCOS operational Green Bay bloom imagery](https://coastalscience.noaa.gov/science-areas/habs/hab-monitoring-system/cyanobacteria-algal-bloom-from-satellite-in-green-bay-and-lake-winnebago-wi/)
3. [Wynne et al. 2022, Green Bay bloom phenology and Lake Erie comparison](https://repository.library.noaa.gov/view/noaa/49251/noaa_49251_DS1.pdf)
4. [USGS 2026 review of Sentinel-2 chlorophyll-a validation](https://www.usgs.gov/publications/sentinel-2-chlorophyll-a-water-quality-monitoring-a-review-validation-evidence-and)
5. [GLORIA Scientific Data 2023](https://doi.org/10.1038/s41597-023-01973-y) · [Dataset](https://doi.org/10.1594/PANGAEA.948492)
6. [NOAA GLERL Western Lake Erie monitoring](https://www.glerl.noaa.gov/res/HABs_and_Hypoxia/wle-weekly-current/)
7. [Roberts et al. 2017 on spatial/temporal blocking](https://doi.org/10.1111/ecog.02881)
8. [Sentinel Hub NDCI algorithm and band definition](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/ndci/)
9. [Optimal sampling research, Frontiers 2021](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2021.689489/full)
10. [Local GP water sampling research, Wiley 2024](https://doi.org/10.1002/aisy.202300850)
11. [GLORIA-to-Sentinel spectral conversion in 2026 work](https://doi.org/10.1016/j.ecoinf.2026.103611)
12. [Clay v1.5 pretrained model quickstart](https://clay-foundation.github.io/model/getting-started/quickstart.html)
