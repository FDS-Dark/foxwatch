"""Human-in-the-loop queue and refit for logistic regression v2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.ml.logistic_regression_v2 import (
    FEATURE_COLUMNS,
    clear_model_cache,
    predict_readings,
    refit_with_feedback,
)
from services.ml.review_store import (
    BASELINE_ID,
    DEFAULT_EVENT_ID,
    DEFAULT_SCENE_ID,
    ReviewStore,
    new_prediction_record,
)
from settings import ML_ARTIFACTS_DIR, ML_LABELED_DATA_PATH, REPO_ROOT


class MlReviewService:
    def __init__(self, store: ReviewStore | None = None):
        self.store = store or ReviewStore()

    def list_models(self) -> dict[str, Any]:
        return self.store.list_models()

    def list_predictions(self, scene_id: str = DEFAULT_SCENE_ID) -> list[dict[str, Any]]:
        return self.store.list_predictions(scene_id)

    def _feature_vector_from_snapshot(self, snapshot: dict[str, Any]) -> list[float]:
        if "feature_vector" in snapshot:
            return [float(x) for x in snapshot["feature_vector"]]
        by_name = snapshot.get("features") or snapshot
        return [float(by_name[name]) for name in FEATURE_COLUMNS]

    def queue_prediction_from_result(
        self,
        result: dict[str, Any],
        *,
        scene_id: str = DEFAULT_SCENE_ID,
        event_id: str = DEFAULT_EVENT_ID,
    ) -> dict[str, Any]:
        if result.get("status") != "available":
            return result

        active = self.store.active_model()
        score = float(result["probability"])
        predicted_class = "proxy_elevated" if result["algal_bloom"] else "proxy_normal"
        feature_snapshot = {
            "features": {inp["feature"]: inp["value"] for inp in result["inputs"]},
            "feature_vector": [float(inp["value"]) for inp in result["inputs"]],
            "parameter_codes": {inp["feature"]: inp["parameter_code"] for inp in result["inputs"]},
            "observed_at": [inp.get("observed_at") for inp in result["inputs"]],
        }
        record = new_prediction_record(
            scene_id=scene_id,
            event_id=event_id,
            model_version_id=active["model_version_id"],
            predicted_class=predicted_class,
            score=score,
            feature_snapshot=feature_snapshot,
            model_output=result,
        )
        self.store.add_prediction(record)
        return {"prediction": record, "model_result": result}

    async def run_prediction(
        self,
        readings: list[dict[str, Any]],
        *,
        scene_id: str = DEFAULT_SCENE_ID,
        event_id: str = DEFAULT_EVENT_ID,
    ) -> dict[str, Any]:
        model_path = self.store.active_artifact_path()
        result = predict_readings(readings, model_path=model_path)
        return self.queue_prediction_from_result(result, scene_id=scene_id, event_id=event_id)

    def review_prediction(
        self,
        prediction_id: str,
        decision: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"approved", "denied"}:
            raise ValueError("decision must be approved or denied")
        return self.store.update_prediction(
            prediction_id,
            review_status=decision,
            review_decision=decision,
            reviewed_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            reviewer_notes=(notes or "").strip() or None,
        )

    def retrain_from_denials(self, max_samples: int = 5) -> dict[str, Any]:
        state = self.store.load()
        denials = [
            p
            for p in state["predictions"]
            if p.get("review_status") == "denied" and not p.get("used_in_training_job_id")
        ][:max_samples]
        if not denials:
            raise ValueError("No denied predictions available for refit")

        parent = self.store.active_model()
        parent_path = self.store.active_artifact_path()
        parent_meta = {}
        meta_path = parent_path.with_suffix(".json")
        if meta_path.is_file():
            import json

            parent_meta = json.loads(meta_path.read_text(encoding="utf-8"))

        feedback: list[tuple[list[float], int]] = []
        for pred in denials:
            model_out = pred.get("model_output") or {}
            predicted = int(model_out.get("algal_bloom", 1 if pred["predicted_class"] == "proxy_elevated" else 0))
            corrected = 1 - predicted
            feedback.append((self._feature_vector_from_snapshot(pred["feature_snapshot"]), corrected))

        new_id = f"mv_refit_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        artifact_rel = f"api/model/artifacts/logistic_regression_{new_id}.pkl"
        artifact_path = (REPO_ROOT / artifact_rel).resolve()

        report = refit_with_feedback(
            base_data_path=ML_LABELED_DATA_PATH,
            feedback_rows=feedback,
            model_path=artifact_path,
            parent_metadata=parent_meta,
        )

        training_job_id = f"tjob_{new_id}"
        self.store.register_model(
            {
                "model_version_id": new_id,
                "name": "logistic_regression_v2_human_informed",
                "created_at_utc": report["trained_at"],
                "parent_model_version_id": parent["model_version_id"],
                "training_job_id": training_job_id,
                "artifact_path": artifact_rel.replace("\\", "/"),
                "parameters_json": {"threshold": 0.5},
                "training_summary": {
                    "human_feedback_rows": len(feedback),
                    "denial_prediction_ids": [p["prediction_id"] for p in denials],
                    "training_rows": report["training_rows"],
                    "roc_auc": report.get("roc_auc"),
                },
                "disclaimer": report["limitations"][0],
            },
            activate=True,
        )
        self.store.mark_denials_used([p["prediction_id"] for p in denials], training_job_id)
        clear_model_cache()

        return {
            "training_job_id": training_job_id,
            "status": "completed",
            "parent_model_version_id": parent["model_version_id"],
            "new_model_version_id": new_id,
            "denial_sample_ids": [p["prediction_id"] for p in denials],
            "message": f"Refitted with {len(feedback)} human correction(s).",
            "report": report,
        }

    def rollback_to_baseline(self) -> dict[str, Any]:
        result = self.store.rollback_active_model(BASELINE_ID)
        clear_model_cache()
        artifact = self.store.active_artifact_path()
        result["artifact_path"] = str(artifact)
        result["message"] = "Active model restored to baseline logistic_regression_v2."
        return result

    def reset_latest_retrain(self) -> dict[str, Any]:
        result = self.store.clear_latest_retrain()
        clear_model_cache()
        artifact = self.store.active_artifact_path()
        result["artifact_path"] = str(artifact)
        result["message"] = (
            f"Removed refit {result['removed_model_version_id']}; "
            f"active model is now {result['active_model_version_id']}."
        )
        return result


def active_model_path_for_inference() -> Path:
    try:
        return ReviewStore().active_artifact_path()
    except Exception:
        return ML_ARTIFACTS_DIR / "logistic_regression_v2.pkl"
