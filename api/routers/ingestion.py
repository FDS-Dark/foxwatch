from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_ingestion_service
from services.usgs_ingestion import UsgsIngestionService

router = APIRouter(tags=["ingestion"])


@router.get("/ingestion/status")
def ingestion_status(ingestion: UsgsIngestionService = Depends(get_ingestion_service)):
    return ingestion.status()


@router.post("/ingestion/poll")
def poll_now(ingestion: UsgsIngestionService = Depends(get_ingestion_service)):
    collector = ingestion.collector
    if not collector.settings.database_url:
        raise HTTPException(
            503,
            "Set database URL in api/.env (TIGER_DATABASE_URL or TIMESCALE_SERVICE_URL)",
        )
    try:
        return ingestion.poll()
    except Exception:
        raise HTTPException(
            502, "Ingestion failed; see /ingestion/status for error type"
        ) from None
