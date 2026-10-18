import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
from fastapi.testclient import TestClient

from services.usgs_ingestion import Settings
from main import app
from services.ml.logistic_regression_v2 import (
    DEFAULT_DATA_PATH, FEATURE_COLUMNS, FEATURE_PARAMETERS,
    load_data, predict_readings, train_and_save,
)


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name) / "model.pkl"
        cls.report = train_and_save(model_path=cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def readings(self):
        x, _ = load_data()
        return [{"parameter_code": parameter, "value": float(x[0, index]),
                 "observed_at": datetime(2026, 10, 17, tzinfo=timezone.utc),
                 "used_fallback": False}
                for index, parameter in enumerate(FEATURE_PARAMETERS.values())]

    def test_only_mean_features_are_used(self):
        self.assertEqual(len(FEATURE_COLUMNS), 7)
        self.assertTrue(all(name.endswith("_mean") for name in FEATURE_COLUMNS))
        self.assertNotIn("00400", FEATURE_PARAMETERS.values())
        self.assertEqual(self.report["training_rows"], 366)
        with DEFAULT_DATA_PATH.open() as source:
            reader = csv.DictReader(source)
            fields = reader.fieldnames
            rows = list(reader)
        for row in rows:
            for key in fields:
                if key.endswith(("_max", "_min", "_median")):
                    row[key] = "ignored nonnumeric value"
        path = Path(self.directory.name) / "modified.csv"
        with path.open("w", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        np.testing.assert_array_equal(load_data()[0], load_data(path)[0])

    def test_inference_order_and_fallback_provenance(self):
        readings = self.readings()
        readings[0]["used_fallback"] = True
        result = predict_readings(list(reversed(readings)), self.path)
        self.assertEqual(result["status"], "available")
        self.assertEqual([r["feature"] for r in result["inputs"]], list(FEATURE_COLUMNS))
        self.assertTrue(result["inputs"][0]["used_fallback"])
        self.assertEqual(result["inputs"][0]["observed_at"], readings[0]["observed_at"])
        self.assertIn(result["algal_bloom"], (0, 1))
        self.assertTrue(0 <= result["probability"] <= 1)

    def test_never_substitutes_training_values_for_unmeasured_features(self):
        for value in (None, float("nan"), float("inf")):
            readings = self.readings()
            readings[0]["value"] = value
            result = predict_readings(readings, self.path)
            self.assertEqual(result["status"], "unavailable")
            self.assertIn(FEATURE_COLUMNS[0], result["missing_features"])
            self.assertNotIn("algal_bloom", result)
        self.assertEqual(len(predict_readings([], self.path)["missing_features"]), 7)

    def test_zero_is_a_valid_measurement(self):
        readings = self.readings()
        readings[0]["value"] = 0
        self.assertEqual(predict_readings(readings, self.path)["status"], "available")

    def test_prediction_endpoint_uses_tiger_data(self):
        read = AsyncMock(return_value=self.readings())
        with patch("settings.resolved_database_url", return_value="postgresql://127.0.0.1:5432/foxwatch"), \
             patch("settings.IngestionSettings.from_env", return_value=Settings(database_url="postgresql://127.0.0.1:5432/foxwatch", enabled=False)), \
             patch("services.observations.ObservationsService.prediction_readings", read), \
             patch("services.usgs_ingestion.fetch_features") as usgs, \
             patch("services.predictions.predict_readings", side_effect=lambda rows, **kw: predict_readings(rows, self.path)), \
             TestClient(app) as client:
            response = client.get("/api/predictions/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "tiger_data")
        self.assertEqual(response.json()["status"], "available")
        self.assertEqual(set(read.call_args.args[0]), set(FEATURE_PARAMETERS.values()))
        usgs.assert_not_called()

    def test_missing_artifact_returns_actionable_error(self):
        with patch("settings.resolved_database_url", return_value="postgresql://127.0.0.1:5432/foxwatch"), \
             patch("settings.IngestionSettings.from_env", return_value=Settings(database_url="postgresql://127.0.0.1:5432/foxwatch", enabled=False)), \
             patch("services.observations.ObservationsService.prediction_readings", AsyncMock(return_value=self.readings())), \
             patch("services.predictions.predict_readings", side_effect=FileNotFoundError), TestClient(app) as client:
            response = client.get("/api/predictions/latest")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Train v2", response.json()["detail"])
