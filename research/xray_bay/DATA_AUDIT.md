# Data audit — USGS FLAMe, Lake Winnebago – Fox River – Green Bay, 2023–2025

All numbers below come from the downloaded files, not from the release's description. To regenerate them, run
`scripts/02_audit.py` (writes `outputs/audit_summary.json`) and `scripts/02b_coverage.py` (writes `outputs/coverage_audit.json`).

## Source and licence

| | |
|---|---|
| Release | Loken, L.C., Pronschinske, M.A., Lafond-Hudson, S.L., Kincaid, D.W., Katona, L.R., Mevis, I.J., Bach, M.T., Trompeter, H.E., Piper, J.N., Olds, H.T., and Givens, C.E., 2026, *High spatial resolution sensor-based surface water quality data along the Lake Winnebago–Fox River–Green Bay continuum in 2023–2025*: U.S. Geological Survey data release, https://doi.org/10.5066/P1XHRFKZ |
| ScienceBase item | https://www.sciencebase.gov/catalog/item/672e5378d34ea9e450891ffe (publication date 2026-10-08) |
| Licence | CC0 1.0 (public domain). Please still cite the release. |
| Method references | Crawford et al. 2015, *High-Speed Limnology*, https://doi.org/10.1021/es504773x ; Loken et al. 2019, https://doi.org/10.1029/2019JG005186 |
| Water mask | Natural Earth 1:10m lakes (public domain), `ne_10m_lakes` polygons for Lake Michigan and Lake Winnebago |

### Access blocker (resolved manually)

Five files are listed. Four are public (`FLAMe_data_dictionary.csv`, `FLAMe_samples.csv`, `FLAMe_metadata.xml`, `FLAMe_map.png`).

**`FLAMe_data.csv` (191,928,255 bytes) is held in ScienceBase cloud storage and cannot be downloaded anonymously:**

- The item's `downloadUri` returns the HTML of the File Manager app.
- The app requests a temporary S3 link through `api.sciencebase.gov/graphql` (`getS3DownloadUrl`), and that request needs a Keycloak bearer token.
- The bucket rejects direct requests with 403.
- The "download all" zip contains a **0-byte** placeholder for this file.

A team member downloaded it through the browser after signing in. The byte size matches the ScienceBase listing exactly. SHA-256 of the copy used: `eeef2afc8d9ea47b3419a6ba7d6879bdcbbc566cf7ad5a1de7126cf070ac1a4c`. `scripts/01_download.py` fetches everything else and prints these manual steps for the gated file.

## Schema

- 82 columns.
- Time: `DateTime_UTC`, about 1 Hz.
- Position: `latitude` and `longitude` in WGS84 decimal degrees, from a Garmin 18X.
- Campaign label: `id`.
- Sensors: YSI EXO2, Seabird SUNA V2, bbe FluoroProbe, LGR UGGA, Garmin Echomap, Vaisala barometer.
- No per-row quality-flag column. QC was applied *upstream*, per the metadata Step 2:
  - flame-on/off trimming;
  - range limits;
  - SensorQC rolling-median/MAD despiking, which writes `NA`;
  - post-calibration corrections for the SUNA and UGGA only.

Each EXO2 variable comes in three versions:

| suffix | meaning | use here |
|---|---|---|
| *(none)* | raw as logged; water reached the sensor seconds after it was at the logged position | no |
| `_hyd` | shifted back in time and space by the hydraulic lag of the plumbing | no |
| `_tau` | hydraulic lag **and** sensor response time corrected | **yes**: best co-located with lat/lon |

### Units and what each variable is (and is not)

| Variable | Units | Note |
|---|---|---|
| `chl_RFU_exo_tau` | RFU | In-vivo chlorophyll-a **fluorescence**. **Not** extracted lab chlorophyll-a. |
| `chl_ugL_exo_tau` | µg/L | The same fluorescence passed through the EXO2 factory conversion. This is still **not** a lab concentration, so it is not used. |
| `bga_RFU_exo_tau` | RFU | Phycocyanin fluorescence. Associated with cyanobacteria. **Not** toxin and **not** a species identification. |
| `turb_FNU_tau` | FNU | Turbidity. A few negative values occur at very low turbidity (calibration offset). |
| `specCond_tau` | µS/cm | Specific conductance. Tracks the Fox River plume. |
| `BlueGreen_FP` etc. | µg/L equiv. | FluoroProbe group estimates. These are an *estimated* split of the fluorescence by algal group. |
| `NO3_mgL` | mg N/L | SUNA optical nitrate. |

## Campaigns (all 8)

Row counts add up to exactly **455,102**, which matches the release abstract. Valid fractions are for the `_tau` columns.

| Campaign | Local dates | Rows | Track km | Rows lat > 44.52 | chl/bga/turb valid | FluoroProbe valid | NO3 valid |
|---|---|---|---|---|---|---|---|
| Fox_2023_Aug | 2023-08-07 → 08-10 | 78,128 | 297 | 15,243 | 0.96 / 0.94 / 0.88 | 0.06 | 0.06 |
| Fox_2024_Jun | 2024-06-24 → 06-27 | 69,925 | 335 | 13,581 | 0.90 / 0.90 / 0.89 | 0.05 | 0.04 |
| Fox_2024_Jul | 2024-07-29 → 07-31 | 58,684 | 257 | 13,534 | 0.90 / 0.88 / 0.88 | 0.11 | 0.07 |
| Fox_2024_Aug | 2024-08-19 → 08-21 | 59,224 | 274 | 11,643 | 0.90 / 0.88 / 0.89 | 0.11 | 0.07 |
| GreenBay_2025_Apr | 2025-04-18 → 04-20 | 48,543 | 177 | 48,543 | 0.90 / 0.91 / 0.90 | 0.00 | 0.08 |
| Fox_2025_May | 2025-04-28 → 05-01 | 44,707 | 163 | 13,862 | 0.90 / 0.90 / 0.90 | 0.03 | 0.08 |
| **GreenBay_2025_Jun** | **2025-06-30 → 07-01** | 45,363 | 266 | 45,363 | 0.90 / 0.90 / 0.90 | 0.01 | 0.07 |
| **Fox_2025_Jul** | **2025-07-07 → 07-10** | 50,528 | 218 | 13,100 | 0.90 / 0.88 / 0.89 | 0.09 | 0.17 |

- The campaign labelled "May 2025" actually ran from **28 April to 1 May**.
- `FLAMe_samples.csv` has **230** rows, not the 239 stated in the abstract (23–36 per campaign). These are 60-second medians of the sensor data at the boat's sampling stops. **The file contains no lab results** (those are joined by `lab_id` to a separate dataset not included here). It is far too sparse for spatial holdout tests.
- The FluoroProbe and SUNA channels are sparse in every campaign (≤17 % valid). **They are excluded.**

## July 2025 decision

FoxWatch wanted **July 2025**, which is `Fox_2025_Jul`. Its Green Bay portion is too small for a 2-D demo:

- **one day** (2025-07-10);
- 626 × 100 m bins and 66 km of track;
- two small loops in lower Green Bay near the Fox River mouth (about 160 km² of water inside its bounding box).

The rest of that campaign is the river corridor (1-D) and a rectangular loop on Lake Winnebago, whose interior was never visited.

**Primary campaign: `GreenBay_2025_Jun`, 30 June – 1 July 2025.** It is the closest campaign in time (it ends on 1 July 2025, six days before `Fox_2025_Jul`). It is also the only summer campaign designed with zig-zag transects across the bay plus a long central line, which is the geometry a spatial-reconstruction demo needs. Within it, `chl_RFU_exo_tau` is about 90 % valid, never negative, and runs from roughly 0.5 RFU in the outer bay to more than 10 RFU in the river plume.

`Fox_2025_Jul` (Green Bay portion) is still run as a secondary experiment. `GreenBay_2025_Apr` is run as a replication of the method.

## Geometry and coverage: dense along the track is not dense across the bay

The domain for each campaign is the Natural Earth Lake Michigan polygon clipped to the campaign's bounding box plus 3 km, on a 250 m grid:

| Campaign (Green Bay part) | 100 m bins | Track km | Water area (km²) | ≤1 km from a measurement | ≤3 km | ≤5 km | Median distance | Max distance |
|---|---|---|---|---|---|---|---|---|
| GreenBay_2025_Jun | 2,497 | 263 | 1,050 | **35 %** | 76 % | 90 % | 1.6 km | 12.2 km |
| GreenBay_2025_Apr | 1,702 | 175 | 1,060 | 25 % | 64 % | 85 % | 2.2 km | 13.0 km |
| Fox_2025_Jul | 626 | 66 | 160 | 51 % | 90 % | 97 % | 1.0 km | 6.8 km |

The June campaign has 40,776 one-second rows in Green Bay. At 100 m resolution these are only about 2,500 distinct places, all on a single line, and two-thirds of the surveyed bay is more than 1 km from any of them.

The track does form distinct transects (west-east zig-zag legs about 5–12 km long, plus a north-south spine). That makes it possible to hold out whole segments and to apply a spatial buffer.

## Processing applied here

1. `_tau` columns only. Rows without position, time, or target are dropped. No extra outlier removal beyond the USGS QC.
2. Projected to **UTM 16N (EPSG:32616)**.
3. Restricted to the water body: points must fall inside the Natural Earth Lake Michigan polygon buffered by 1 km (the 1:10m coastline is coarse near the river mouth). This removes the Fox River corridor.
4. **Thinned into 100 m along-track bins** using the median value and median position. This removes the 1 Hz duplication and collapses stationary sampling stops into one bin.
5. Log transform `log(v + 1)` for the trained models on optical targets. The offset is fixed and is not estimated from the data.

## Limitations

- **Time is not simultaneous.** Each campaign spans 2–4 days, and `GreenBay_2025_Jun` spans 2 days. The reconstruction treats one campaign as one snapshot, so changes over the day (wind, plume movement, diurnal fluorescence quenching) appear as spatial "noise."
- **Fluorescence quenching.** Daytime non-photochemical quenching lowers chlorophyll fluorescence in bright surface water. No correction is applied.
- **Depth.** Samples are drawn from 0.2 m depth only. Nothing is said about the water column.
- **Coastline resolution.** The 1:10m mask is coarse near the shore and at the river mouth. Some valid nearshore bins sit outside the unbuffered polygon.
- **No independent lab validation.** RFU values are relative instrument units, so they are comparable within a campaign but not necessarily across campaigns.
