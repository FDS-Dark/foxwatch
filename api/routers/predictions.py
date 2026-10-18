from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_collector, get_predictions_service
from services.usgs_ingestion import UsgsCollector
from services.predictions import PredictionsService
from sqlalchemy.exc import ProgrammingError

router = APIRouter(tags=["predictions"])


@router.get("/api/predictions/latest")
async def latest_bloom_prediction(
    collector: UsgsCollector = Depends(get_collector),
    predictions: PredictionsService = Depends(get_predictions_service),
):
    if not collector.settings.database_url:
        raise HTTPException(503, "The observation database is not configured")
    try:
        return await predictions.latest()
    except FileNotFoundError:
        raise HTTPException(
            503, "Train v2 first: uv run python -m services.ml.logistic_regression_v2"
        ) from None
    except ProgrammingError as exc:
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == "42P01":
            raise HTTPException(
                503, "Observations are not ready; waiting for the first ingestion"
            ) from None
        raise HTTPException(502, "Unable to generate the latest prediction") from None
    except Exception:
        raise HTTPException(502, "Unable to generate the latest prediction") from None
