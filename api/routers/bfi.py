from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_bfi_service
from models.bfi import BfiInsightRequest
from services.bfi import BfiService

router = APIRouter(prefix="/api/v1/bfi", tags=["bfi"])


@router.post("/insights")
def bfi_insights(
    body: BfiInsightRequest,
    bfi_service: BfiService = Depends(get_bfi_service),
):
    try:
        return bfi_service.generate_insights(body)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
