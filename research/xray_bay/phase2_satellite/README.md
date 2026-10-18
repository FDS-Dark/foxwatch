# X-Ray the Bay, Phase 2: Sentinel-2 covariates

This tests whether time-matched Sentinel-2 L2A reflectance improves reconstruction of hidden FLAMe survey segments, compared with location-only models. It uses the same bins and folds as Phase 1, and Phase 1 outputs in `../` are not modified.

**Outcome: CONDITIONAL GO.**
- [DECISION.md](DECISION.md): the decision.
- [RESULTS.md](RESULTS.md): metrics, segment 32 and failure cases.
- [SCENE_AUDIT.md](SCENE_AUDIT.md): imagery discovery and pixel validity.
- [MATCHUP_AUDIT.md](MATCHUP_AUDIT.md): bin matchup and time rules.

## Layout

```
scripts/
  p2_common.py              paths/constants; imports Phase 1 xray_common (loaders, folds, models, metrics)
  01_stac_inventory.py      Earth Search STAC query -> outputs/scene_inventory.csv, outputs/stac_items/, figures/acquisition_timeline.png
  02_fetch_scenes.py        windowed COG reads -> data/<item>_20m.tif (B02-B11 reflectance, SCL, CLD), data/<item>_tci.tif
  03_masks_matchup.py       water/cloud/glint masks, bin matchup under each time rule -> outputs/matched_bins.parquet,
                            outputs/matchup_summary.json, figures/cloud_water_quality_check.png, figures/matched_footprint.png
  04_experiment.py <rule>   hard + standard spatial CV on matched bins -> outputs/cv/<rule>*.{json,csv,parquet}
  05_report.py              comparison tables, paired fold stats, intervals -> outputs/satellite_model_comparison.csv,
                            outputs/paired_folds.csv, outputs/metrics.json, figures/hard_holdout_comparison.png
  06_reveal.py [--export]   four-state reveal figures (segments 32, typical, failure, best) + exports/
  07_scene_consistency.py   06-30 vs 07-01 radiometric agreement; feature/target rank correlations
data/                       downloaded scene subsets (git-ignored, ~0.75 GB; regenerate with 02)
outputs/selected_scene_ids.json  main, sensitivity and export scene IDs
exports/                    experimental GeoTIFF/GeoJSON (EPSG:32616 / 4326, tagged with scene, UTC, units, model version)
```

## Reproduce

This uses the Phase 1 virtual environment (`../.venv`) and `../data/processed/flame_core.parquet`, which `../scripts/02_audit.py` produces. No credentials are needed: Earth Search assets are public, without requester-pays.

```bash
cd research/xray_bay/phase2_satellite/scripts
PY=../../.venv/bin/python
$PY 01_stac_inventory.py
$PY 02_fetch_scenes.py          # ~3 min
$PY 03_masks_matchup.py
for r in glint_main glint_0701w24 glint_0701 glint_0628 strict_main; do
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 XRAY_JOBS=4 $PY 04_experiment.py $r &   # ~10 min each
done; wait
$PY 05_report.py
$PY 06_reveal.py --export
$PY 07_scene_consistency.py
```

Seeds are fixed. GP optimiser results can vary slightly between BLAS builds.

## Rules (see MATCHUP_AUDIT.md)

| Rule | Role |
|---|---|
| `glint_main` | **predeclared primary**: nearest same-survey scene, lag ≤ 24 h, glint-corrected |
| `glint_0701w24` | post-hoc: 07-01 scene only, lag ≤ 24 h |
| `glint_0701` | sensitivity: 07-01 scene only |
| `glint_0628` | 24–72 h tier (not time-matched) |
| `strict_main` | predeclared strict mask (B11 ≤ 0.03) |

## Attribution

- **Sentinel-2:** Copernicus Sentinel-2 L2A data, 2025, accessed through Element 84 Earth Search (`sentinel-2-c1-l2a`), https://earth-search.aws.element84.com/v1. Contains modified Copernicus Sentinel data.
- **FLAMe:** Loken, L.C., and others, 2026, U.S. Geological Survey data release, https://doi.org/10.5066/P1XHRFKZ (CC0).
