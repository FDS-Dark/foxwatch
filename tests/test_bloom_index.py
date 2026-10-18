"""Unit tests for the Bloom Favorability Index (BFI)."""

import unittest

from foxwatch.bfi.index import (
    BloomFavorabilityResult,
    RuleBasedScoringEngine,
    calculate_bloom_favorability,
    classify_favorability,
    score_streamflow,
    score_water_temperature,
)


class TestIndividualScorers(unittest.TestCase):
    def test_water_temperature_bands(self) -> None:
        self.assertEqual(score_water_temperature(15.0), (0, None))
        self.assertEqual(score_water_temperature(22.0)[0], 1)
        self.assertEqual(score_water_temperature(27.0)[0], 2)

    def test_streamflow_priority_rules(self) -> None:
        median = 150.0
        self.assertEqual(score_streamflow(160.0, median)[0], 0)
        self.assertEqual(score_streamflow(80.0, median)[0], 2)
        self.assertEqual(score_streamflow(150.0, median)[0], 1)


class TestBloomFavorabilityScenarios(unittest.TestCase):
    def test_low_favorability(self) -> None:
        result = calculate_bloom_favorability(
            water_temperature_c=18.0,
            phosphorus_ug_l=10.0,
            nitrogen_mg_l=0.2,
            streamflow_cfs=200.0,
            seasonal_median_streamflow_cfs=150.0,
            rainfall_7day_in=0.1,
            solar_radiation_level="low",
        )
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["max_possible_score"], 12)
        self.assertEqual(result["favorability_percent"], 0.0)
        self.assertEqual(result["classification"], "LOW FAVORABILITY")
        self.assertEqual(result["reasons"], [])

    def test_moderate_favorability(self) -> None:
        # One point on each factor → 6/12 → 50% → MODERATE (between 25% and ~58%)
        result = calculate_bloom_favorability(
            water_temperature_c=22.0,
            phosphorus_ug_l=30.0,
            nitrogen_mg_l=0.75,
            streamflow_cfs=150.0,
            seasonal_median_streamflow_cfs=150.0,
            rainfall_7day_in=1.0,
            solar_radiation_level="moderate",
        )
        self.assertEqual(result["score"], 6)
        self.assertEqual(result["classification"], "MODERATE FAVORABILITY")
        self.assertEqual(len(result["factors"]), 6)
        self.assertGreater(len(result["reasons"]), 0)

    def test_high_favorability(self) -> None:
        result_high = calculate_bloom_favorability(
            water_temperature_c=27.0,
            phosphorus_ug_l=75.0,
            nitrogen_mg_l=1.2,
            streamflow_cfs=150.0,
            seasonal_median_streamflow_cfs=150.0,
            rainfall_7day_in=1.0,
            solar_radiation_level="moderate",
        )
        self.assertEqual(result_high["score"], 9)
        self.assertEqual(result_high["classification"], "HIGH FAVORABILITY")
        self.assertTrue(
            any("Water temperature exceeds" in r for r in result_high["reasons"])
        )

    def test_very_high_favorability(self) -> None:
        result = calculate_bloom_favorability(
            water_temperature_c=30.0,
            phosphorus_ug_l=100.0,
            nitrogen_mg_l=2.0,
            streamflow_cfs=50.0,
            seasonal_median_streamflow_cfs=150.0,
            rainfall_7day_in=3.0,
            solar_radiation_level="high",
        )
        self.assertEqual(result["score"], 12)
        self.assertEqual(result["favorability_percent"], 100.0)
        self.assertEqual(result["classification"], "VERY HIGH FAVORABILITY")

    def test_missing_factors_renormalize(self) -> None:
        result = calculate_bloom_favorability(
            water_temperature_c=30.0,
            phosphorus_ug_l=None,
            nitrogen_mg_l=None,
            streamflow_cfs=None,
            seasonal_median_streamflow_cfs=None,
            rainfall_7day_in=None,
            solar_radiation_level="high",
        )
        self.assertEqual(result["score"], 4)
        self.assertEqual(result["max_possible_score"], 4)
        self.assertEqual(result["favorability_percent"], 100.0)
        self.assertEqual(len(result["factors"]), 2)

    def test_partial_streamflow_excluded(self) -> None:
        result = calculate_bloom_favorability(
            water_temperature_c=18.0,
            streamflow_cfs=100.0,
            seasonal_median_streamflow_cfs=None,
        )
        self.assertEqual(result["max_possible_score"], 2)
        attributes = [f["attribute"] for f in result["factors"]]
        self.assertNotIn("discharge", attributes)

    def test_engine_returns_result_object(self) -> None:
        engine = RuleBasedScoringEngine()
        raw = engine.calculate(water_temperature_c=22.0)
        self.assertIsInstance(raw, BloomFavorabilityResult)
        payload = raw.to_dict()
        self.assertIn("score", payload)


class TestClassificationProportional(unittest.TestCase):
    def test_full_scale_matches_fixed_bands(self) -> None:
        self.assertEqual(
            classify_favorability(3, 12).value,
            "LOW FAVORABILITY",
        )
        self.assertEqual(
            classify_favorability(4, 12).value,
            "MODERATE FAVORABILITY",
        )
        self.assertEqual(
            classify_favorability(10, 12).value,
            "HIGH FAVORABILITY",
        )
        self.assertEqual(
            classify_favorability(11, 12).value,
            "VERY HIGH FAVORABILITY",
        )


if __name__ == "__main__":
    unittest.main()
