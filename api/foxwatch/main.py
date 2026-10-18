"""
FoxWatch API — current observations (Tiger Data), BFI scoring, and RAG insights.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from foxwatch.bfi.index import calculate_bloom_favorability
from foxwatch.bfi.insights import generate_bfi_insights
from foxwatch.bfi.gemini import gemini_configured, model_candidates
from foxwatch.config import RAG_INDEX_PATH, REPO_ROOT
from foxwatch.observations import observation_lifespan, register_observation_routes
from foxwatch.rag.embeddings import HashEmbedder, create_production_embedder, load_embedded_chunks

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "api" / ".env", override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with observation_lifespan(app):
        yield


app = FastAPI(title="FoxWatch API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_observation_routes(app)


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
    return {
        "service": "FoxWatch API",
        "docs": "/docs",
        "health": "/api/health",
        "observations_latest": "GET /api/observations/latest",
        "bfi_insights": "POST /api/v1/bfi/insights",
        "ui_current": "http://127.0.0.1:5173/#/current",
        "ui_bfi": "http://127.0.0.1:5173/#/bfi",
    }


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    collector = getattr(request.app.state, "collector", None)
    tiger_ok = bool(collector and collector.settings.database_url)
    return {
        "status": "ok",
        "rag_index": str(RAG_INDEX_PATH),
        "rag_index_present": RAG_INDEX_PATH.is_file(),
        "gemini_configured": gemini_configured(),
        "gemini_models": model_candidates(),
        "tiger_data_configured": tiger_ok,
        "ingestion": collector.status.copy() if collector else None,
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
