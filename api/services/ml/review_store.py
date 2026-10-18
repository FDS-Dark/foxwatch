"""Persist human-in-the-loop prediction reviews and model lineage (JSON file)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import ML_ARTIFACTS_DIR, ML_REVIEW_STATE_PATH, REPO_ROOT

BASELINE_ID = "mv_v2_baseline"
BASELINE_NAME = "logistic_regression_v2"
BASELINE_PKL = ML_ARTIFACTS_DIR / "logistic_regression_v2.pkl"
BASELINE_JSON = ML_ARTIFACTS_DIR / "logistic_regression_v2.json"
DEFAULT_SCENE_ID = "USGS-040851385"
DEFAULT_EVENT_ID = "fox_river_green_bay"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _default_state() -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if BASELINE_JSON.is_file():
        meta = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    return {
        "active_model_version_id": BASELINE_ID,
        "models": [
            {
                "model_version_id": BASELINE_ID,
                "name": BASELINE_NAME,
                "created_at_utc": meta.get("trained_at", _utcnow()),
                "parent_model_version_id": None,
                "training_job_id": None,
                "artifact_path": str(BASELINE_PKL.relative_to(REPO_ROOT)).replace("\\", "/"),
                "parameters_json": {"threshold": 0.5},
                "training_summary": {
                    "training_rows": meta.get("training_rows"),
                    "human_feedback_rows": 0,
                    "source": "labeled_openai.csv",
                },
                "disclaimer": " ".join(meta.get("limitations", [])[:2])
                or "Class-weighted logistic regression; not lab-confirmed HAB detection.",
            }
        ],
        "predictions": [],
    }


class ReviewStore:
    def __init__(self, path: Path | None = None):
        self.path = path or ML_REVIEW_STATE_PATH

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            state = _default_state()
            self.save(state)
            return state
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def active_model(self) -> dict[str, Any]:
        state = self.load()
        active = state["active_model_version_id"]
        for model in state["models"]:
            if model["model_version_id"] == active:
                return model
        raise KeyError(f"Active model {active} missing from registry")

    def active_artifact_path(self) -> Path:
        rel = self.active_model()["artifact_path"]
        path = (REPO_ROOT / rel).resolve()
        if path.is_file():
            return path
        if path.name != BASELINE_PKL.name and BASELINE_PKL.is_file():
            return BASELINE_PKL.resolve()
        raise FileNotFoundError(f"Model artifact missing: {path}")

    def list_models(self) -> dict[str, Any]:
        state = self.load()
        return {
            "active_model_version_id": state["active_model_version_id"],
            "models": state["models"],
        }

    def list_predictions(self, scene_id: str | None = None) -> list[dict[str, Any]]:
        preds = self.load()["predictions"]
        if scene_id:
            return [p for p in preds if p.get("scene_id") == scene_id]
        return preds

    def add_prediction(self, record: dict[str, Any]) -> dict[str, Any]:
        state = self.load()
        state["predictions"].append(record)
        self.save(state)
        return record

    def update_prediction(self, prediction_id: str, **fields: Any) -> dict[str, Any]:
        state = self.load()
        for idx, pred in enumerate(state["predictions"]):
            if pred["prediction_id"] == prediction_id:
                state["predictions"][idx] = {**pred, **fields}
                self.save(state)
                return state["predictions"][idx]
        raise KeyError(f"Prediction not found: {prediction_id}")

    def register_model(self, model: dict[str, Any], *, activate: bool = True) -> dict[str, Any]:
        state = self.load()
        state["models"].append(model)
        if activate:
            state["active_model_version_id"] = model["model_version_id"]
        self.save(state)
        return model

    def mark_denials_used(self, prediction_ids: list[str], training_job_id: str) -> None:
        state = self.load()
        ids = set(prediction_ids)
        for idx, pred in enumerate(state["predictions"]):
            if pred["prediction_id"] in ids:
                state["predictions"][idx]["used_in_training_job_id"] = training_job_id
        self.save(state)

    def rollback_active_model(self, model_version_id: str = BASELINE_ID) -> dict[str, Any]:
        """Point inference at an earlier registered model (default: baseline v2)."""
        state = self.load()
        if not any(m["model_version_id"] == model_version_id for m in state["models"]):
            raise KeyError(f"Model not in registry: {model_version_id}")

        previous = state["active_model_version_id"]
        state["active_model_version_id"] = model_version_id

        for idx, pred in enumerate(state["predictions"]):
            if pred.get("used_in_training_job_id"):
                state["predictions"][idx]["used_in_training_job_id"] = None

        state["predictions"] = [
            p
            for p in state["predictions"]
            if not (
                p.get("review_status") == "pending_review"
                and p.get("model_version_id") != model_version_id
            )
        ]

        self.save(state)
        return {
            "previous_active_model_version_id": previous,
            "active_model_version_id": model_version_id,
        }

    def clear_latest_retrain(self) -> dict[str, Any]:
        """Drop the newest human-refit model, restore its parent as active, undo its denial usage."""
        state = self.load()
        refits = [m for m in state["models"] if m.get("parent_model_version_id")]
        if not refits:
            raise ValueError("No refit models to reset")

        refits.sort(key=lambda m: m.get("created_at_utc") or "")
        latest = refits[-1]
        latest_id = latest["model_version_id"]
        parent_id = latest.get("parent_model_version_id") or BASELINE_ID
        if not any(m["model_version_id"] == parent_id for m in state["models"]):
            raise KeyError(f"Parent model missing from registry: {parent_id}")

        previous_active = state["active_model_version_id"]
        if previous_active == latest_id:
            state["active_model_version_id"] = parent_id

        training_job_id = latest.get("training_job_id")
        if training_job_id:
            for idx, pred in enumerate(state["predictions"]):
                if pred.get("used_in_training_job_id") == training_job_id:
                    state["predictions"][idx]["used_in_training_job_id"] = None

        state["predictions"] = [
            p
            for p in state["predictions"]
            if not (
                p.get("review_status") == "pending_review"
                and p.get("model_version_id") == latest_id
            )
        ]
        state["models"] = [m for m in state["models"] if m["model_version_id"] != latest_id]
        self.save(state)

        removed_artifact: str | None = None
        rel = latest.get("artifact_path")
        if rel and latest_id.startswith("mv_refit_"):
            artifact = (REPO_ROOT / rel).resolve()
            artifacts_root = ML_ARTIFACTS_DIR.resolve()
            if artifact.name == BASELINE_PKL.name:
                pass
            elif artifacts_root in artifact.parents or artifact.parent == artifacts_root:
                if artifact.is_file():
                    removed_artifact = str(artifact)
                    artifact.unlink(missing_ok=True)
                meta = artifact.with_suffix(".json")
                if meta.is_file():
                    meta.unlink(missing_ok=True)

        return {
            "removed_model_version_id": latest_id,
            "previous_active_model_version_id": previous_active,
            "active_model_version_id": state["active_model_version_id"],
            "restored_parent_model_version_id": parent_id,
            "removed_artifact_path": removed_artifact,
        }


def new_prediction_record(
    *,
    scene_id: str,
    event_id: str,
    model_version_id: str,
    predicted_class: str,
    score: float,
    feature_snapshot: dict[str, Any],
    model_output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "prediction_id": _uid("pred"),
        "scene_id": scene_id,
        "event_id": event_id,
        "model_version_id": model_version_id,
        "predicted_class": predicted_class,
        "score": score,
        "feature_snapshot": feature_snapshot,
        "model_output": model_output,
        "review_status": "pending_review",
        "review_decision": None,
        "reviewed_at_utc": None,
        "reviewer_notes": None,
        "used_in_training_job_id": None,
        "created_at_utc": _utcnow(),
    }
