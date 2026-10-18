import unittest

from api.services.bfi_supplemental_inputs import _parse_wqp_nutrient_rows


class WqpNutrientParseTests(unittest.TestCase):
    def test_picks_latest_per_usgs_code(self) -> None:
        csv_text = (
            "ActivityStartDate,ResultMeasureValue,ResultMeasure/MeasureUnitCode,USGSPCode\n"
            "2023-07-06,0.097,mg/l as P,00671\n"
            "2023-08-09,0.016,mg/l as P,00671\n"
            "2023-08-09,0.047,mg/l as N,00631\n"
            "2023-07-06,0.35,mg/l as N,00608\n"
        )
        parsed = _parse_wqp_nutrient_rows(csv_text)
        self.assertAlmostEqual(parsed["orthophosphate_mg_l_as_p"], 0.016)
        self.assertAlmostEqual(parsed["nitrate_nitrite_mg_l_as_n"], 0.047)
        self.assertAlmostEqual(parsed["ammonia_mg_l_as_n"], 0.35)
        self.assertEqual(parsed["latest_sample_date"], "2023-08-09")


if __name__ == "__main__":
    unittest.main()
