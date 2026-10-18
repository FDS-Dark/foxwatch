"""
FoxWatch API — BFI scoring and evidence-backed bloom insights.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from foxwatch.bfi.index import calculate_bloom_favorability
from foxwatch.bfi.insights import generate_bfi_insights
from foxwatch.bfi.gemini import gemini_configured, model_candidates
from foxwatch.config import RAG_INDEX_PATH, REPO_ROOT
from foxwatch.rag.embeddings import HashEmbedder, create_production_embedder, load_embedded_chunks

load_dotenv(REPO_ROOT / ".env")

app = FastAPI(title="FoxWatch API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BfiInsightRequest(BaseModel):
    water_temperature_c: Optional[float] = None
    phosphorus_ug_l: Optional[float] = None
    nitrogen_mg_l: Optional[float] = None
    streamflow_cfs: Optional[float] = None
    seasonal_median_streamflow_cfs: Optional[float] = None
    rainfall_7day_in: Optional[float] = None
    solar_radiation_level: Optional[str] = None
    use_gemini: bool = True


@lru_cache(maxsize=1)
def _embedder():
    try:
        return create_production_embedder()
    except Exception:
        return HashEmbedder(dimensions=384)


@lru_cache(maxsize=1)
def _index():
    if not RAG_INDEX_PATH.is_file():
        raise FileNotFoundError(f"RAG index missing: {RAG_INDEX_PATH}")
    return load_embedded_chunks(RAG_INDEX_PATH)


@app.get("/")
def root() -> dict[str, Any]:
    """Browser-friendly index (UI is served by Vite on port 5173)."""
    return {
        "service": "FoxWatch API",
        "docs": "/docs",
        "health": "/api/health",
        "bfi_insights": "POST /api/v1/bfi/insights",
        "ui": "http://127.0.0.1:5173/#/bfi",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "rag_index": str(RAG_INDEX_PATH),
        "rag_index_present": RAG_INDEX_PATH.is_file(),
        "gemini_configured": gemini_configured(),
        "gemini_models": model_candidates(),
    }


@app.post("/api/v1/bfi/insights")
def bfi_insights(body: BfiInsightRequest) -> dict[str, Any]:
    try:
        index = _index()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    bfi = calculate_bloom_favorability(
        water_temperature_c=body.water_temperature_c,
        phosphorus_ug_l=body.phosphorus_ug_l,
        nitrogen_mg_l=body.nitrogen_mg_l,
        streamflow_cfs=body.streamflow_cfs,
        seasonal_median_streamflow_cfs=body.seasonal_median_streamflow_cfs,
        rainfall_7day_in=body.rainfall_7day_in,
        solar_radiation_level=body.solar_radiation_level,
    )
    payload = generate_bfi_insights(
        bfi,
        index,
        _embedder(),
        use_gemini=body.use_gemini,
        include_prompt=False,
    )
    payload["bfi"]["factors"] = bfi.get("factors", [])
    payload["bfi"]["reasons"] = bfi.get("reasons", [])
    payload["bfi"]["favorability_percent"] = bfi.get("favorability_percent")
    return payload
