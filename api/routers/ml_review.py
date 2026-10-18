from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_collector, get_ml_review_service, get_predictions_service
from services.ml.review_store import DEFAULT_SCENE_ID
from services.ml_review import MlReviewService
from services.predictions import PredictionsService
from services.usgs_ingestion import UsgsCollector

router = APIRouter(prefix="/api/v1/ml", tags=["ml-review"])


class ReviewBody(BaseModel):
    decision: str = Field(description="approved or denied")
    notes: Optional[str] = None


class RetrainBody(BaseModel):
    max_denials: int = Field(default=5, ge=1, le=20)


@router.get("/models")
def list_models(service: MlReviewService = Depends(get_ml_review_service)) -> dict[str, Any]:
    return service.list_models()


@router.get("/predictions")
def list_predictions(
    scene_id: str = DEFAULT_SCENE_ID,
    service: MlReviewService = Depends(get_ml_review_service),
) -> dict[str, Any]:
    return {"scene_id": scene_id, "predictions": service.list_predictions(scene_id)}


@router.post("/predictions/run")
async def run_prediction_for_review(
    scene_id: str = DEFAULT_SCENE_ID,
    collector: UsgsCollector = Depends(get_collector),
    predictions: PredictionsService = Depends(get_predictions_service),
    review: MlReviewService = Depends(get_ml_review_service),
) -> dict[str, Any]:
    if not collector.settings.database_url:
        raise HTTPException(503, "Tiger Data is required to score live conditions")
    try:
        latest = await predictions.latest()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    if latest.get("status") != "available":
        raise HTTPException(503, latest.get("reason", "Prediction inputs unavailable"))

    return review.queue_prediction_from_result(latest, scene_id=scene_id)


@router.post("/predictions/{prediction_id}/review")
def submit_review(
    prediction_id: str,
    body: ReviewBody,
    service: MlReviewService = Depends(get_ml_review_service),
) -> dict[str, Any]:
    try:
        updated = service.review_prediction(prediction_id, body.decision, body.notes)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"prediction": updated}


@router.post("/retrain")
def retrain_from_human_feedback(
    body: RetrainBody,
    service: MlReviewService = Depends(get_ml_review_service),
) -> dict[str, Any]:
    try:
        return service.retrain_from_denials(max_samples=body.max_denials)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        raise HTTPException(502, "Refit failed") from None


@router.post("/models/rollback")
def rollback_active_model(
    service: MlReviewService = Depends(get_ml_review_service),
) -> dict[str, Any]:
    """Undo a refit: switch back to mv_v2_baseline and drop pending queue rows from refit models."""
    try:
        return service.rollback_to_baseline()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/models/reset-retrain")
def reset_latest_retrain(
    service: MlReviewService = Depends(get_ml_review_service),
) -> dict[str, Any]:
    """Remove the most recent refit from lineage and restore the parent model for inference."""
    try:
        return service.reset_latest_retrain()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
