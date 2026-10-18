from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import get_collector
from models.incident_recovery import IncidentRecoveryRequest
from services.incident_recovery import IncidentRecoveryService
from services.usgs_ingestion import UsgsCollector

router = APIRouter(prefix="/api/v1/incident-recovery", tags=["incident-recovery"])

_service = IncidentRecoveryService()


@router.post("/suggest")
def suggest_recovery(
    body: IncidentRecoveryRequest,
    request: Request,
    collector: UsgsCollector = Depends(get_collector),
) -> dict:
    try:
        return _service.suggest(body, collector=collector)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Incident recovery suggestion failed: {exc}") from exc
