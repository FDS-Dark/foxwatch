from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import HTTPException

from models.bfi import BfiInsightRequest
from services.bfi_insights import answer_bfi_question, generate_bfi_insights
from services.bfi_scoring import calculate_bloom_favorability
from services.bfi_supplemental_inputs import enrich_live_bfi_kwargs
from services.bfi_tiger_inputs import bfi_kwargs_from_readings
from services.rag_embeddings import HashEmbedder, create_production_embedder, load_embedded_chunks
from services.usgs_ingestion import UsgsCollector
from settings import RAG_INDEX_PATH, rag_index_available

_BFI_CALC_KEYS = (
    "water_temperature_c",
    "phosphorus_ug_l",
    "orthophosphate_mg_l_as_p",
    "total_phosphorus_mg_l_as_p",
    "nitrogen_mg_l",
    "nitrate_nitrite_mg_l_as_n",
    "ammonia_mg_l_as_n",
    "streamflow_cfs",
    "seasonal_median_streamflow_cfs",
    "rainfall_7day_in",
    "solar_radiation_level",
)

# Keys forwarded to ``calculate_bloom_favorability`` (includes USGS manifest aliases).
_BFI_SCORING_KEYS = _BFI_CALC_KEYS


@lru_cache(maxsize=1)
def _embedder():
    try:
        return create_production_embedder()
    except Exception:
        return HashEmbedder(dimensions=384)


@lru_cache(maxsize=1)
def _index():
    if not rag_index_available():
        raise FileNotFoundError(f"RAG index missing under {RAG_INDEX_PATH.parent}")
    return load_embedded_chunks(RAG_INDEX_PATH)


class BfiService:
    def load_index(self):
        return _index()

    def _calc_kwargs(self, body: BfiInsightRequest, collector: UsgsCollector | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
        calc: dict[str, Any] = {
            "water_temperature_c": body.water_temperature_c,
            "phosphorus_ug_l": body.phosphorus_ug_l,
            "nitrogen_mg_l": body.nitrogen_mg_l,
            "streamflow_cfs": body.streamflow_cfs,
            "seasonal_median_streamflow_cfs": body.seasonal_median_streamflow_cfs,
            "rainfall_7day_in": body.rainfall_7day_in,
            "solar_radiation_level": body.solar_radiation_level,
        }
        provenance: dict[str, Any] | None = None

        if body.use_live_data:
            if collector is None or not collector.settings.database_url:
                raise HTTPException(
                    503,
                    "Live BFI inputs require Tiger Data (set TIMESCALE_SERVICE_URL in api/.env)",
                )
            readings = collector.bfi_readings_sync()
            seasonal_median = collector.seasonal_median_discharge_cfs()
            live = bfi_kwargs_from_readings(
                readings,
                seasonal_median_streamflow_cfs=seasonal_median,
                rainfall_7day_in=calc.get("rainfall_7day_in"),
                solar_radiation_level=calc.get("solar_radiation_level"),
            )
            provenance = live.pop("_provenance", None)
            for key, value in live.items():
                if calc.get(key) is None and value is not None:
                    calc[key] = value
            enrich_live_bfi_kwargs(
                calc,
                provenance,
                station_id=collector.settings.station,
            )

        return {k: calc[k] for k in _BFI_SCORING_KEYS if k in calc}, provenance

    def generate_insights(
        self,
        body: BfiInsightRequest,
        *,
        collector: UsgsCollector | None = None,
    ) -> dict[str, Any]:
        index = self.load_index()
        calc_kwargs, provenance = self._calc_kwargs(body, collector)
        bfi = calculate_bloom_favorability(**calc_kwargs)
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
        if provenance:
            payload["inputs_provenance"] = provenance
            payload["inputs"] = {k: calc_kwargs.get(k) for k in _BFI_CALC_KEYS}
        return payload

    def ask(
        self,
        question: str,
        body: BfiInsightRequest,
        *,
        collector: UsgsCollector | None = None,
    ) -> dict[str, Any]:
        index = self.load_index()
        calc_kwargs, _provenance = self._calc_kwargs(body, collector)
        bfi = calculate_bloom_favorability(**calc_kwargs)
        return answer_bfi_question(
            question,
            bfi,
            index,
            _embedder(),
            use_gemini=body.use_gemini,
        )
