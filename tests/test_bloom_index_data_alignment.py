"""Cross-check BFI labels and scoring against Foxwatch USGS exports."""

import unittest
from pathlib import Path

from api.services.bfi_scoring import calculate_bloom_favorability, calculate_bloom_favorability_from_observations
from api.models.bfi_factors import (
    DEFAULT_MANIFEST_PATH,
    USGS_REFERENCE_THRESHOLDS,
    assert_bfi_labels_match_manifest,
    load_parameter_manifest,
    load_usgs_daily_values,
    median_discharge_for_month,
    mg_p_as_p_to_ug_l,
)

REPO = Path(__file__).resolve().parents[1]
DAILY_CSV = REPO / "data" / "attributes" / "2026-10-17T22-56-42.689Z-daily.csv"


class TestManifestAlignment(unittest.TestCase):
    def test_bfi_factor_labels_match_usgs_manifest(self) -> None:
        assert_bfi_labels_match_manifest(load_parameter_manifest(DEFAULT_MANIFEST_PATH))

    def test_bloom_indicator_thresholds_documented(self) -> None:
        manifest = load_parameter_manifest()
        for code, limits in USGS_REFERENCE_THRESHOLDS.items():
            row = next(r for r in manifest.values() if r.parameter_code == code)
            self.assertEqual(row.role, "bloom_indicator" if code in {"32319", "32316"} else "condition_predictor")


class TestUsgsDailyExport(unittest.TestCase):
    def test_real_station_values_use_manifest_parameter_codes(self) -> None:
        if not DAILY_CSV.is_file():
            self.skipTest("USGS daily export not present")

        temp = load_usgs_daily_values(DAILY_CSV, parameter_code="00010")
        discharge = load_usgs_daily_values(DAILY_CSV, parameter_code="00060")
        fpc = load_usgs_daily_values(DAILY_CSV, parameter_code="32319", statistic_id="00002")

        self.assertIn("2025-10-17", temp)
        self.assertIn("2025-10-17", discharge)
        self.assertIn("2025-10-17", fpc)

        # fPC stays well below USGS operational "high" (125 µg/L) on this date.
        self.assertLess(fpc["2025-10-17"], USGS_REFERENCE_THRESHOLDS["32319"]["high_ug_l"])

        median_jul = median_discharge_for_month(discharge, month=7)
        self.assertIsNotNone(median_jul)

        result = calculate_bloom_favorability(
            water_temperature_c=temp["2025-10-17"],
            streamflow_cfs=discharge["2025-10-17"],
            seasonal_median_streamflow_cfs=median_jul,
        )
        discharge_factor = next(
            f for f in result["factors"] if f["attribute"] == "discharge"
        )
        self.assertEqual(discharge_factor["parameter_code"], "00060")
        self.assertEqual(discharge_factor["factor"], "Discharge")
        self.assertEqual(discharge_factor["unit"], "ft3/s")

    def test_demo_fixture_shape_via_python_mirror(self) -> None:
        observations = [
            {
                "metric": "discharge",
                "metric_code": "00060",
                "observation_date": "2020-06-05",
                "value": 9100.0,
                "unit": "ft³/s",
            },
            {
                "metric": "precipitation",
                "observation_date": "2020-06-05",
                "value": 0.4,
                "unit": "mm",
            },
            {
                "metric": "precipitation",
                "observation_date": "2020-06-04",
                "value": 24.6,
                "unit": "mm",
            },
            {
                "metric": "precipitation",
                "observation_date": "2020-06-03",
                "value": 11.2,
                "unit": "mm",
            },
        ]
        result = calculate_bloom_favorability_from_observations(
            observations,
            as_of_date="2020-06-05",
            water_temperature_c=24.0,
            seasonal_median_streamflow_cfs=5200.0,
        )
        rain_factor = next(
            f for f in result["factors"] if f["attribute"] == "precipitation"
        )
        self.assertEqual(rain_factor["source"], "NOAA")
        self.assertGreater(rain_factor["points"], 0)

    def test_orthophosphate_manifest_units_convert_to_bfi_ug_l(self) -> None:
        # 0.075 mg/L as P → 75 µg/L (BFI high phosphorus band).
        ug = mg_p_as_p_to_ug_l(0.075)
        result = calculate_bloom_favorability(orthophosphate_mg_l_as_p=0.075)
        p_factor = next(
            f for f in result["factors"] if f["attribute"] == "orthophosphate_dissolved"
        )
        self.assertEqual(p_factor["parameter_code"], "00671")
        self.assertEqual(p_factor["value"], ug)
        self.assertEqual(p_factor["points"], 2)


if __name__ == "__main__":
    unittest.main()
