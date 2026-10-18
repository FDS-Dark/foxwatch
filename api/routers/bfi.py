from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_bfi_service, get_collector
from models.bfi import BfiAskRequest, BfiInsightRequest
from services.bfi import BfiService
from services.usgs_ingestion import UsgsCollector

router = APIRouter(prefix="/api/v1/bfi", tags=["bfi"])


@router.post("/insights")
def bfi_insights(
    body: BfiInsightRequest,
    bfi_service: BfiService = Depends(get_bfi_service),
    collector: UsgsCollector = Depends(get_collector),
):
    try:
        return bfi_service.generate_insights(body, collector=collector)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ask")
def bfi_ask(
    body: BfiAskRequest,
    bfi_service: BfiService = Depends(get_bfi_service),
    collector: UsgsCollector = Depends(get_collector),
):
    try:
        insight_body = BfiInsightRequest(
            use_live_data=body.use_live_data,
            use_gemini=body.use_gemini,
        )
        return bfi_service.ask(body.question, insight_body, collector=collector)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
