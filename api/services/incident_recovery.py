"""Bloom incident recovery: cleanup and harm reduction from live BFI + RAG + Gemini."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Mapping, Optional, Sequence

from fastapi import HTTPException

from models.bfi import BfiInsightRequest
from models.incident_recovery import IncidentRecoveryRequest
from services.bfi import BfiService
from services.bfi_retrieval import build_evidence_package, chunk_to_source, hybrid_retrieve
from services.bfi_scoring import calculate_bloom_favorability
from services.gemini_client import gemini_configured, generate_structured_json
from services.rag_embeddings import HashEmbedder, create_production_embedder, load_embedded_chunks, search_chunks
from settings import RAG_INDEX_PATH, rag_index_available

_RECOVERY_JSON_SUFFIX = (
    "\n\nRespond with a single JSON object only (no markdown fences) using keys: "
    "situation_summary (tie to today's bloom favorability score and live drivers), "
    "recovery_suggestions (array of 5–8 objects with title, category "
    "(algae_cleanup|consequence_reduction), priority (immediate|short_term|long_term), "
    "actions (concrete steps to remove or reduce algae biomass OR reduce public/ecosystem harm), "
    "rationale, optional caution, evidence_chunk_ids (from evidence blocks only), "
    "source_relevance (array of {chunk_id, why_relevant})), "
    "monitoring_recommendations (array of strings), "
    "confidence (object with level Low|Moderate|High, percent 0-100, reason). "
    "Include at least two algae_cleanup and two consequence_reduction suggestions. "
    "Prefer realistic freshwater HAB measures (avoidance, nutrient/load reduction, in-lake options "
    "where evidence supports them). Do not invent studies."
)

_CLEANUP_RETRIEVAL_SEED = (
    "Harmful algal bloom cyanobacteria cleanup removal skimming biomass reduction "
    "phosphorus inactivation mixing aeration watershed nutrient management "
    "public health advisory consequences exposure pets drinking water irrigation "
    "Lower Fox River Green Bay Wisconsin"
)


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


def _passage_blurb_chunk(chunk: Mapping[str, Any], *, max_len: int = 320) -> str:
    raw = str(chunk.get("retrieval_summary") or "").strip()
    raw = re.sub(r"^This section explains [^.]+\.\s*", "", raw, flags=re.IGNORECASE)
    if len(raw) < 48:
        raw = str(chunk.get("text") or "").strip()[:max_len]
    return raw[:max_len]


def _require_live_context(collector) -> dict[str, Any]:
    if collector is None or not collector.settings.database_url:
        raise HTTPException(
            503,
            "Incident recovery requires live bloom favorability inputs (TIMESCALE_SERVICE_URL in api/.env).",
        )
    try:
        bfi_service = BfiService()
        calc, provenance = bfi_service._calc_kwargs(  # noqa: SLF001
            BfiInsightRequest(use_live_data=True),
            collector,
        )
    except HTTPException as exc:
        raise HTTPException(
            503,
            "Could not load live conditions for recovery suggestions.",
        ) from exc
    bfi = calculate_bloom_favorability(**calc)
    return {
        "bfi": bfi,
        "inputs": calc,
        "inputs_provenance": provenance,
    }


def _format_current_conditions(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Human-readable live inputs and scored drivers for the UI."""
    rows: list[dict[str, Any]] = []
    bfi = bundle.get("bfi") or {}
    for factor in bfi.get("factors") or []:
        label = factor.get("label") or factor.get("attribute") or "Driver"
        points = factor.get("points")
        detail = factor.get("reason") or factor.get("detail") or ""
        rows.append(
            {
                "kind": "driver",
                "label": str(label),
                "points": points,
                "detail": str(detail) if detail else None,
            }
        )
    inputs = bundle.get("inputs") or {}
    provenance = bundle.get("inputs_provenance") or {}
    labels = {
        "water_temperature_c": "Water temperature (°C)",
        "streamflow_cfs": "Streamflow (cfs)",
        "seasonal_median_streamflow_cfs": "Seasonal median streamflow (cfs)",
        "rainfall_7day_in": "Rainfall last 7 days (in)",
        "orthophosphate_mg_l_as_p": "Orthophosphate (mg/L as P)",
        "nitrate_nitrite_mg_l_as_n": "Nitrate + nitrite (mg/L as N)",
        "ammonia_mg_l_as_n": "Ammonia (mg/L as N)",
        "solar_radiation_level": "Sunlight (seasonal proxy)",
    }
    for key, label in labels.items():
        value = inputs.get(key)
        if value is None:
            continue
        note = None
        if key == "rainfall_7day_in" and provenance.get("rainfall_source") == "open_meteo":
            note = "Open-Meteo at station"
        if provenance.get("nutrient_latest_sample_date") and key.startswith(
            ("orthophosphate", "nitrate", "ammonia")
        ):
            note = f"WQP sample {provenance['nutrient_latest_sample_date']}"
        rows.append({"kind": "input", "label": label, "value": value, "note": note})
    return rows


def _build_retrieval_query(bfi: Mapping[str, Any], *, notes: Optional[str]) -> str:
    classification = bfi.get("classification", "Bloom favorability")
    score = bfi.get("score", "")
    max_score = bfi.get("max_possible_score", 12)
    driver_lines = [
        str(f.get("label") or f.get("attribute") or "")
        for f in (bfi.get("factors") or [])
        if f.get("points")
    ]
    driver_phrase = ", ".join(driver_lines[:6]) or "current environmental drivers"
    parts = [
        _CLEANUP_RETRIEVAL_SEED,
        f"Today's bloom favorability is {classification} ({score}/{max_score} points).",
        f"Active bloom-friendly drivers: {driver_phrase}.",
        "Recommend algae cleanup, bloom reduction, and consequence mitigation grounded in evidence.",
    ]
    if notes:
        parts.append(f"Operator notes: {notes.strip()}")
    return " ".join(parts)


def _merge_evidence(
    bfi: Mapping[str, Any],
    cleanup_query: str,
    *,
    top_k: int,
) -> tuple[list[dict[str, Any]], str]:
    index = _index()
    embedder = _embedder()

    driver_pack = build_evidence_package(bfi, index, embedder, top_k=max(4, top_k // 2))
    cleanup_ranked = search_chunks(cleanup_query, index, embedder, top_k=top_k, min_priority="medium")
    if len(cleanup_ranked) < 3:
        cleanup_ranked = search_chunks(cleanup_query, index, embedder, top_k=top_k, min_priority="low")

    merged: dict[str, dict[str, Any]] = {}
    for row in driver_pack.supporting_chunks:
        cid = str(row.get("chunk_id"))
        merged[cid] = dict(row)

    for chunk, score in cleanup_ranked:
        cid = chunk.chunk_id
        if cid in merged:
            continue
        merged[cid] = {
            "chunk_id": cid,
            "text": chunk.text,
            "retrieval_summary": chunk.retrieval_summary,
            "tags": chunk.tags,
            "vector_score": round(score, 4),
            "metadata": chunk_to_source(chunk),
        }
        if len(merged) >= top_k:
            break

    # Backfill from hybrid rank if still short
    if len(merged) < top_k:
        for item in hybrid_retrieve(bfi, index, embedder, top_k=top_k):
            cid = item.chunk.chunk_id
            if cid not in merged:
                merged[cid] = {
                    "chunk_id": cid,
                    "text": item.chunk.text,
                    "retrieval_summary": item.chunk.retrieval_summary,
                    "tags": item.chunk.tags,
                    "hybrid_score": round(item.hybrid_score, 4),
                    "metadata": chunk_to_source(item.chunk),
                }
            if len(merged) >= top_k:
                break

    supporting = list(merged.values())[:top_k]
    context_summary = (
        f"Retrieved {len(supporting)} passages on bloom drivers, algae cleanup, and harm reduction "
        f"for Green Bay / Lower Fox River (semantic + driver-aware search)."
    )
    return supporting, context_summary


def _bfi_driver_lines(bfi: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for factor in bfi.get("factors") or []:
        if not factor.get("points"):
            continue
        label = factor.get("label") or factor.get("attribute") or "driver"
        pts = factor.get("points")
        lines.append(f"- {label} ({pts} pts toward favorability)")
    return lines or ["- No positive bloom-driver factors scored today"]


def _inputs_block(bundle: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for row in _format_current_conditions(bundle):
        if row.get("kind") != "input":
            continue
        note = f" ({row['note']})" if row.get("note") else ""
        lines.append(f"- {row['label']}: {row['value']}{note}")
    return "\n".join(lines) or "- Live numeric inputs partially unavailable"


def _build_gemini_prompt(
    bundle: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    *,
    notes: Optional[str],
) -> str:
    bfi = bundle["bfi"]
    evidence_lines: list[str] = []
    for idx, chunk in enumerate(evidence, start=1):
        meta = chunk.get("metadata") or {}
        title = meta.get("document_title") or "Research passage"
        blurb = _passage_blurb_chunk(chunk)
        evidence_lines.append(
            f"[Evidence {idx}] chunk_id={chunk.get('chunk_id')}\n"
            f"Title: {title}\n"
            f"Section: {meta.get('section') or meta.get('chapter') or ''}\n"
            f"Passage: {blurb}\n"
            f"Tags: {', '.join(chunk.get('tags') or [])}"
        )

    notes_block = f"\nOptional operator notes:\n{notes.strip()}\n" if notes else ""

    return f"""Location: Lower Fox River · Green Bay, Wisconsin.

Live bloom favorability (BFI):
- Classification: {bfi.get('classification')}
- Score: {bfi.get('score')} / {bfi.get('max_possible_score')} (available drivers today)
- Full scale reference: 12 points when all six driver families report

Scored drivers today:
{chr(10).join(_bfi_driver_lines(bfi))}

Current measurements feeding the score:
{_inputs_block(bundle)}
{notes_block}
Task: Based on TODAY's bloom favorability and conditions above, recommend practical steps to
(1) clean up or reduce cyanobacteria / algae biomass where feasible and
(2) reduce consequences for people, pets, drinking water, recreation, and fisheries.
Tailor urgency to the favorability class. Ground every suggestion in the evidence below.
Use plain language for watershed and health staff. Cite evidence using chunk_id only.

Indexed research evidence:
{chr(10).join(evidence_lines) if evidence_lines else "[No evidence retrieved]"}
"""


def _chunk_map(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(c.get("chunk_id")): c for c in evidence if c.get("chunk_id")}


def _attach_sources(
    suggestions: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id = _chunk_map(evidence)
    relevance_by_id: dict[str, str] = {}
    out: list[dict[str, Any]] = []

    for raw in suggestions:
        row = dict(raw)
        ids = [str(x) for x in (row.pop("evidence_chunk_ids", None) or []) if x]
        for rel in row.pop("source_relevance", None) or []:
            if isinstance(rel, Mapping):
                cid = str(rel.get("chunk_id") or "")
                why = str(rel.get("why_relevant") or rel.get("relevance") or "").strip()
                if cid and why:
                    relevance_by_id[cid] = why

        sources: list[dict[str, Any]] = []
        for cid in ids:
            chunk = by_id.get(cid)
            if not chunk:
                continue
            meta = chunk.get("metadata") or {}
            sources.append(
                {
                    "chunk_id": cid,
                    "document_title": meta.get("document_title") or "",
                    "section": meta.get("section") or meta.get("chapter") or "",
                    "excerpt": _passage_blurb_chunk(chunk),
                    "relevance": relevance_by_id.get(cid) or row.get("rationale") or "",
                    "metadata": meta,
                }
            )
        row["sources"] = sources
        if row.get("category") not in ("algae_cleanup", "consequence_reduction"):
            title = str(row.get("title") or "").lower()
            row["category"] = (
                "consequence_reduction"
                if any(w in title for w in ("advisory", "health", "public", "exposure", "pet"))
                else "algae_cleanup"
            )
        out.append(row)
    return out


def _fallback_suggestions(
    bundle: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    bfi = bundle["bfi"]
    classification = bfi.get("classification", "current conditions")
    top = list(evidence)[:5]
    templates: list[tuple[str, str, str, list[str], str]] = [
        (
            "algae_cleanup",
            "immediate",
            "Avoid disturbing surface scums",
            [
                "Do not mechanically break up dense scums where toxins may aerosolize.",
                "Focus on upstream nutrient and flow drivers that sustain biomass.",
            ],
            "Physical disturbance can release toxins; evidence emphasizes reducing nutrient supply and safe handling.",
        ),
        (
            "algae_cleanup",
            "short_term",
            "Target phosphorus loading that fuels regrowth",
            [
                "Prioritize watershed actions that reduce bioavailable phosphorus after storms.",
                "Track orthophosphate and flow pulses from the Fox River mouth station.",
            ],
            "Bloom persistence is linked to phosphorus and hydrology in retrieved guidance.",
        ),
        (
            "consequence_reduction",
            "immediate",
            "Issue clear contact advisories",
            [
                "Post swimming, pet, and irrigation guidance when scum or high fluorescence is observed.",
                "Point the public to official HAB health messaging rather than informal reports.",
            ],
            "Harm reduction focuses on limiting exposure during active blooms.",
        ),
        (
            "consequence_reduction",
            "long_term",
            "Plan monitoring through recovery",
            [
                "Continue chlorophyll/phycocyanin and nutrient monitoring until favorability eases.",
                "Document advisory start/end criteria for after-action review.",
            ],
            "Monitoring supports safe reopening and tracks driver relaxation.",
        ),
    ]
    suggestions: list[dict[str, Any]] = []
    for (category, priority, title, actions, rationale), chunk in zip(templates, top, strict=False):
        meta = chunk.get("metadata") or {}
        suggestions.append(
            {
                "title": title,
                "category": category,
                "priority": priority,
                "actions": actions,
                "rationale": rationale,
                "sources": [
                    {
                        "chunk_id": chunk.get("chunk_id"),
                        "document_title": meta.get("document_title") or "",
                        "section": meta.get("section") or "",
                        "excerpt": _passage_blurb_chunk(chunk),
                        "relevance": rationale,
                        "metadata": meta,
                    }
                ],
            }
        )

    return {
        "situation_summary": (
            f"With {classification} ({bfi.get('score')}/{bfi.get('max_possible_score')} BFI points), "
            "focus on safe algae management and reducing public exposure while drivers remain elevated. "
            "Suggestions below come from retrieved research (Gemini synthesis unavailable)."
        ),
        "recovery_suggestions": suggestions,
        "monitoring_recommendations": [
            "Re-check bloom favorability when flow, temperature, or rainfall shifts materially.",
            "Pair satellite or fluorescence signals with field observations before lifting advisories.",
        ],
        "confidence": {
            "level": "Moderate",
            "percent": 50,
            "reason": "Retrieval-only fallback keyed to live BFI score.",
        },
        "generation_mode": "retrieval_fallback",
    }


class IncidentRecoveryService:
    def load_index(self):
        return _index()

    def suggest(
        self,
        body: IncidentRecoveryRequest,
        *,
        collector=None,
    ) -> dict[str, Any]:
        try:
            self.load_index()
        except FileNotFoundError as exc:
            raise HTTPException(503, str(exc)) from exc

        bundle = _require_live_context(collector)
        bfi = bundle["bfi"]
        query = _build_retrieval_query(bfi, notes=body.optional_notes)
        evidence, context_summary = _merge_evidence(bfi, query, top_k=body.top_k)

        prompt = _build_gemini_prompt(bundle, evidence, notes=body.optional_notes)
        gemini_mode = "skipped"
        narrative: dict[str, Any]

        if body.use_gemini and gemini_configured():
            parsed, gemini_mode = generate_structured_json(
                prompt,
                json_suffix=_RECOVERY_JSON_SUFFIX,
            )
            if parsed:
                suggestions = _attach_sources(
                    parsed.get("recovery_suggestions") or [],
                    evidence,
                )
                narrative = {
                    "situation_summary": parsed.get("situation_summary") or "",
                    "recovery_suggestions": suggestions,
                    "monitoring_recommendations": parsed.get("monitoring_recommendations") or [],
                    "confidence": parsed.get("confidence") or {},
                    "generation_mode": f"rag_gemini_{gemini_mode}",
                    "rag_grounded": True,
                }
            else:
                narrative = _fallback_suggestions(bundle, evidence)
                narrative["gemini_error"] = gemini_mode
        else:
            narrative = _fallback_suggestions(bundle, evidence)
            narrative["generation_mode"] = (
                "retrieval_fallback_gemini_disabled"
                if not body.use_gemini
                else "retrieval_fallback_missing_api_key"
            )

        return {
            "bfi": {
                "classification": bfi.get("classification"),
                "score": bfi.get("score"),
                "max_possible_score": bfi.get("max_possible_score"),
                "full_max_score": bfi.get("full_max_score", 12),
                "favorability_percent_full": bfi.get("favorability_percent_full"),
                "drivers_reporting": bfi.get("drivers_reporting"),
                "drivers_total": bfi.get("drivers_total", 6),
                "factors": bfi.get("factors") or [],
            },
            "current_conditions": _format_current_conditions(bundle),
            "inputs": bundle.get("inputs"),
            "inputs_provenance": bundle.get("inputs_provenance"),
            "evidence": {
                "context_summary": context_summary,
                "supporting_chunks": evidence,
                "retrieval_query": query,
            },
            "recovery": narrative,
            "gemini_status": gemini_mode if body.use_gemini else "disabled",
        }
