from __future__ import annotations

from functools import lru_cache
from typing import Any

from models.bfi import BfiInsightRequest
from services.bfi_insights import generate_bfi_insights
from services.bfi_scoring import calculate_bloom_favorability
from services.rag_embeddings import HashEmbedder, create_production_embedder, load_embedded_chunks
from settings import RAG_INDEX_PATH


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


class BfiService:
    def load_index(self):
        return _index()

    def generate_insights(self, body: BfiInsightRequest) -> dict[str, Any]:
        index = self.load_index()
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
