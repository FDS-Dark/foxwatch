# Scene audit (gates G0 and G1)

Regenerate with `scripts/01_stac_inventory.py` (catalog search), `02_fetch_scenes.py` (subsets) and `03_masks_matchup.py` (masks).

## G0: discovery

The Earth Search STAC catalog (`https://earth-search.aws.element84.com/v1`) was searched for collection `sentinel-2-c1-l2a`, cross-checked against the legacy `sentinel-2-l2a`.

- **Search area:** bbox −88.10, 44.50, −87.50, 45.16, which covers every 100 m survey bin.
- **Dates:** 2025-06-26 to 2025-07-04, a ±3 day window around the survey.
- **Result:** both collections return the same 12 acquisitions (6 dates × tiles 16TDQ and 16TDR).
- **Tile used:** only **16TDQ** (lat 44.16–45.15) contains the whole survey. 16TDR covers about 15% of the area, north of 45.06° N.
- **Processing:** every scene is processing baseline 05.11, with asset scale 1e-4 and offset −0.1.

Full list: [`outputs/scene_inventory.csv`](outputs/scene_inventory.csv). Raw STAC items: `outputs/stac_items/`. Timeline figure: [`figures/acquisition_timeline.png`](figures/acquisition_timeline.png).

**Survey window:** 2025-06-30 14:25 to 2025-07-01 18:36 UTC. The 30 June leg runs 14:25–21:51 UTC; the 1 July leg runs 13:33–18:36.

| 16TDQ item | Acquired (UTC) | Relation to survey | Scene cloud % (metadata) | Thin cirrus % | Role |
|---|---|---|---:|---:|---|
| S2B_T16TDQ_20250626T165714_L2A | 06-26 17:01 | 93 h before | 85.1 | 0.2 | not used (cloud) |
| S2C_T16TDQ_20250628T164829_L2A | 06-28 16:51 | 46–74 h before | 30.9 | 29.2 | **24–72 h sensitivity tier only** |
| **S2A_T16TDQ_20250630T164706_L2A** | **06-30 16:51** | **during day 1** | 66.2 | 27.1 | **main** (time-matched) |
| **S2C_T16TDQ_20250701T165332_L2A** | **07-01 17:01** | **during day 2** | 5.1 | 0.0 | **main** (time-matched) |
| S2B_T16TDQ_20250703T164446_L2A | 07-03 16:51 | 46 h after | 12.9 | 12.4 | not used |
| S2A_T16TDQ_20250703T165928_L2A | 07-03 17:01 | 46–74 h after | 3.8 | 3.2 | fetched for QA only, not modelled |

**G0 passes.** Each survey day has its own pass:
- 06-30 at 16:51 UTC, 2.4 h after the boat started;
- 07-01 at 17:01 UTC, 1.6 h before the boat finished.

## G1: pixel validity

Scene-wide cloud percentages from the metadata were **not** used for any decision. All pixel-level checks are on a 20 m grid over the survey window:
- B05, B06, B07, B8A, B11, SCL and CLD are at native 20 m.
- B02, B03 and B04 were averaged 2×2 from 10 m to 20 m. This is exact aggregation, with no interpolation.

### Predeclared mask

A pixel counts as valid water only if all of these hold:
- every band is finite;
- SCL is not 0, 1, 3, 8, 9, 10 or 11 (no-data, saturated, cloud shadow, cloud medium/high, cirrus, snow);
- CLD ≤ 10%;
- MNDWI(B03, B11) > 0;
- **B11 ≤ 0.03**;
- it is at least 200 m from any pixel that fails these tests (shoreline adjacency and cloud edges).

### What the pixel audit showed

| Scene | Bins valid, strict mask | Bins valid, glint mask | Water B11 along track (5th / 50th / 95th percentile) |
|---|---:|---:|---|
| 06-30 S2A | 481 / 2,497 | 574 | 0.008 / 0.033 / 0.33 (cirrus) |
| 07-01 S2C | **77** / 2,497 | **1,692** | 0.015 / **0.059** / 0.22 |
| 06-28 S2C | 1,697 | 1,700 | 0.004 / 0.011 / 0.038 |
| 07-03 S2A | 85 | 2,413 | 0.029 / 0.056 / 0.062 |

**06-30:** most of the survey area is under cirrus (SCL 10 on 1,077 of 2,497 track bins) or cloud. Only the southern bay and some mid-bay patches survive.

**07-01:** nearly cloud-free, apart from scattered small cumulus and their shadows, which SCL, CLD and the 200 m buffer remove. However, open-water B11 is a **smooth 0.04–0.08 field with a NE–SW gradient**, and the water looks silvery in true colour (`figures/cloud_water_quality_check.png`). This is sun glint and/or aerosol, not cloud:
- sun zenith 24°, view zenith 9°, view azimuth 41° from the specular direction;
- the B11 field has none of the patchy structure of cloud.

The predeclared B11 ≤ 0.03 screen therefore rejected 88% of the only clear, same-day scene.

### Documented deviation: primary mask = "glint"

This decision was made after the pixel audit and **before** any satellite feature was compared with fluorescence:
- B11 ≤ **0.10** replaces 0.03, so bright haze and cloud remnants are still excluded;
- every band is glint-corrected by **SWIR subtraction**: ρ′(band) = ρ(band) − ρ(B11). This assumes the glint is spectrally flat, as common aquatic processors do;
- NDCI and the ratios are computed from the corrected bands;
- all other criteria are unchanged.

The strict mask is kept as the `strict_main` variant and is reported.

### Caveats that remain

- **Sen2Cor L2A is a land-oriented bottom-of-atmosphere product.** After SWIR subtraction the values are an empirical predictor, **not water-leaving reflectance (Rrs)**. A water-specific atmospheric correction was not run (ACOLITE, C2RCC, or Sentinel Hub with credentials). Earth Search held everything needed, so Copernicus Data Space was not used.
- Flat-glint subtraction is approximate. Residual glint varies smoothly across the bay, so the satellite features may carry a cross-bay gradient that is geometric, not optical. Coordinate features can absorb part of that.
- The 200 m adjacency buffer and 10m-scale coastline issues mean the **nearshore and river-mouth bins are the ones most often masked**, and those hold the highest fluorescence.
