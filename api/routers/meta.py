from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from dependencies import get_ingestion_service
from services.gemini_client import gemini_configured, model_candidates
from services.usgs_ingestion import UsgsIngestionService
from settings import RAG_INDEX_PATH, rag_index_available, rag_use_tiger_vectors, resolved_database_url
from services.rag_tiger_store import tiger_embedding_count

router = APIRouter()


@router.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "FoxWatch API",
        "docs": "/docs",
        "health": "/api/health",
        "observations_latest": "GET /api/observations/latest",
        "bfi_insights": "POST /api/v1/bfi/insights",
        "ui_current": "http://127.0.0.1:6173/#/current",
        "ui_bfi": "http://127.0.0.1:6173/#/bfi",
    }


@router.get("/api/health")
def health(
    request: Request,
    ingestion: UsgsIngestionService = Depends(get_ingestion_service),
) -> dict[str, Any]:
    collector = request.app.state.collector
    tiger_ok = bool(collector.settings.database_url)
    return {
        "status": "ok",
        "rag_index": str(RAG_INDEX_PATH),
        "rag_index_present": rag_index_available(),
        "rag_vector_backend": "tiger" if rag_use_tiger_vectors() else "faiss",
        "rag_tiger_vectors": tiger_embedding_count() if resolved_database_url() else None,
        "gemini_configured": gemini_configured(),
        "gemini_models": model_candidates(),
        "tiger_data_configured": tiger_ok,
        "ingestion": ingestion.status(),
    }
