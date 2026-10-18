from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_collector, get_ingestion_service, get_observations_service
from services.usgs_ingestion import UsgsCollector, UsgsIngestionService
from services.observations import ObservationsService
from sqlalchemy.exc import ProgrammingError

router = APIRouter(tags=["observations"])


@router.get("/usgs/latest")
def latest_usgs(ingestion: UsgsIngestionService = Depends(get_ingestion_service)):
    try:
        return ingestion.latest_usgs()
    except Exception:
        raise HTTPException(502, "Unable to fetch USGS observations") from None


@router.get("/api/observations/latest")
async def latest_stored_observations(
    collector: UsgsCollector = Depends(get_collector),
    observations: ObservationsService = Depends(get_observations_service),
):
    if not collector.settings.database_url:
        raise HTTPException(503, "The observation database is not configured")
    try:
        return await observations.latest_stored()
    except ProgrammingError as exc:
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == "42P01":
            raise HTTPException(
                503, "Observations are not ready; waiting for the first ingestion"
            ) from None
        raise HTTPException(502, "Unable to read stored observations") from None
    except Exception:
        raise HTTPException(502, "Unable to read stored observations") from None
