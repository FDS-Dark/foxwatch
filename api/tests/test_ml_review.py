import tempfile
import unittest
from pathlib import Path

from services.ml.review_store import ReviewStore, new_prediction_record
from services.ml_review import MlReviewService


class MlReviewRefitTests(unittest.TestCase):
    def test_denial_maps_to_opposite_label_for_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewStore(Path(tmp) / "review_state.json")
            service = MlReviewService(store)
            pred = new_prediction_record(
                scene_id="USGS-040851385",
                event_id="test",
                model_version_id="mv_v2_baseline",
                predicted_class="proxy_normal",
                score=0.2,
                feature_snapshot={
                    "feature_vector": [10.0, 2000.0, 9.5, 5.0, 400.0, 30.0, 15.0],
                },
                model_output={"algal_bloom": 0, "probability": 0.2},
            )
            pred["review_status"] = "denied"
            state = store.load()
            state["predictions"].append(pred)
            store.save(state)

            vector = service._feature_vector_from_snapshot(pred["feature_snapshot"])
            self.assertEqual(len(vector), 7)
            self.assertEqual(vector[0], 10.0)

    def test_rollback_restores_baseline_and_clears_refit_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewStore(Path(tmp) / "review_state.json")
            state = store.load()
            state["active_model_version_id"] = "mv_refit_test"
            state["models"].append(
                {
                    "model_version_id": "mv_refit_test",
                    "name": "refit",
                    "artifact_path": "api/model/artifacts/logistic_regression_v2.pkl",
                }
            )
            state["predictions"].append(
                {
                    "prediction_id": "pred_pending_refit",
                    "review_status": "pending_review",
                    "model_version_id": "mv_refit_test",
                }
            )
            state["predictions"].append(
                {
                    "prediction_id": "pred_denied",
                    "review_status": "denied",
                    "used_in_training_job_id": "tjob_x",
                }
            )
            store.save(state)

            result = store.rollback_active_model()
            self.assertEqual(result["active_model_version_id"], "mv_v2_baseline")
            reloaded = store.load()
            self.assertEqual(reloaded["active_model_version_id"], "mv_v2_baseline")
            ids = [p["prediction_id"] for p in reloaded["predictions"]]
            self.assertNotIn("pred_pending_refit", ids)
            denied = next(p for p in reloaded["predictions"] if p["prediction_id"] == "pred_denied")
            self.assertIsNone(denied["used_in_training_job_id"])

    def test_clear_latest_retrain_drops_refit_and_restores_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewStore(Path(tmp) / "review_state.json")
            state = store.load()
            state["active_model_version_id"] = "mv_refit_new"
            state["models"].append(
                {
                    "model_version_id": "mv_refit_new",
                    "name": "refit",
                    "created_at_utc": "2026-10-18T05:00:00+00:00",
                    "parent_model_version_id": "mv_v2_baseline",
                    "training_job_id": "tjob_mv_refit_new",
                    "artifact_path": "api/model/artifacts/logistic_regression_v2.pkl",
                }
            )
            state["predictions"].append(
                {
                    "prediction_id": "pred_used",
                    "review_status": "denied",
                    "used_in_training_job_id": "tjob_mv_refit_new",
                }
            )
            store.save(state)

            result = store.clear_latest_retrain()
            self.assertEqual(result["removed_model_version_id"], "mv_refit_new")
            self.assertEqual(result["active_model_version_id"], "mv_v2_baseline")
            reloaded = store.load()
            self.assertEqual(len(reloaded["models"]), 1)
            self.assertIsNone(reloaded["predictions"][0]["used_in_training_job_id"])


if __name__ == "__main__":
    unittest.main()
