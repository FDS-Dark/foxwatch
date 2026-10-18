# Decision: CONDITIONAL GO

**Satellite covariates are worth pursuing. They are not yet ready to replace the Phase 1 location-only reconstruction as the validated FoxWatch option.**

## Evidence

All numbers are hard spatial holdout on identical matched bins and folds, MAE in RFU.

| Claim | Evidence | Status |
|---|---|---|
| Time-matched imagery exists | S2A 2025-06-30 16:51 UTC and S2C 2025-07-01 17:01 UTC over the survey; 65% of bins matched, median lag 2.9 h | ✅ |
| Predeclared primary rule beats the best location-only model by >10% | rf_xysat 0.609 vs rf_xy 0.630: **−3.4%** (CI −7.9% to +3.1%), 25/48 folds improved | ❌ |
| Single clean scene beats location-only | rf_xysat 0.588 vs gp_xy 0.668: **−12.1%** (CI −32% to +12%); vs rf_xy −13.3% (CI −18.5% to −7.1%), 29/44 folds | ⚠️ post-hoc rule; CI vs GP includes 0 |
| Recovers the segment 32 plume filament | gp_resid 1.62 vs rf_xy 4.18 / gp_xy 4.73 / idw 5.23 RFU; bias −1.1 vs −4.2 RFU | ✅ for this segment |
| Same model is safe elsewhere | gp_resid is worse than rf_xy in 33/48 folds; overshoots at the river mouth (segments 27–31, 49, 51) | ❌ |
| Time-matching is what matters | an image 46–74 h old gives a similar gain (−14% vs rf_xy) | ❌ The signal is a persistent plume |
| Satellite-informed uncertainty localises error | Spearman(|err|, SD) = −0.16 to −0.19; coverage OK on average | ❌ |
| Spectral signal is chlorophyll-specific | NDCI ρ = 0.25 with fluorescence; B05 ρ = 0.83, and B05 tracks turbidity at ρ = 0.82 | ❌ It is turbid plume brightness |

## What could be integrated now (research-labelled only)

- **Demo exhibit:** `figures/segment32_satellite_reveal.png` as a "what the boat missed, the satellite saw" visual, captioned with the failure case (segment 31) and the caveats above.
- **Experimental layers** in `exports/`:
  - `satellite_covariates.tif` (07-01, glint-corrected B03/B04/B05/NDCI, 100 m);
  - `predicted_chl_rfu.tif` (rf_xysat full fit, masked; RFU, *experimental*);
  - `prediction_support_mask.tif`;
  - `segment32_predictions.geojson`.

  All are EPSG:32616 or EPSG:4326 with scene ID, acquisition UTC, units and model version tags. **They are not a validated product.**
- **Keep** the Phase 1 GP+IDW reconstruction as the validated layer.

## Do not claim

- That satellite imagery "detects chlorophyll" or blooms. The predictor is plume brightness, and the target is RFU fluorescence.
- A >10% general improvement. The predeclared primary shows −3%.
- Calibrated uncertainty for any satellite-informed map.

## Single next experiment

**Run a predeclared replication with a single clear scene and a plume-aware model:**

1. **Before looking at any targets, fix:**
   - the rule: the single clearest scene within 24 h;
   - the mask: glint mask with SWIR subtraction;
   - the models: rf_xy, gp_xy, rf_xysat and a **non-linear** satellite trend + GP residual (rf_sat → GP on residuals);
   - the success criterion: >10% vs the best location-only model, with a bootstrap CI excluding zero.
2. **Run on another FLAMe Green Bay survey with a clear same-day Sentinel-2 pass.** Check `GreenBay_2025_Apr` (2025-04-18 to 04-20) first, then the Green Bay legs of the 2023–2024 campaigns.
3. **Repeat with turbidity (FNU) as a target.** This tests whether the gain is plume brightness rather than anything chlorophyll-specific.
4. **Optionally re-run 07-01 with ACOLITE.** This removes the crude glint correction as a confound.

The replication decides whether the 12–14% single-scene gain and the segment 32 recovery are real and transferable, or a feature of one well-behaved plume day.
