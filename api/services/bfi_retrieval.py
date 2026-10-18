"""
Hybrid RAG retrieval for Bloom Favorability Index (BFI) explanations.

Combines driver-aware tag matching, metadata/source filtering, vector similarity,
and retrieval-priority weighting. Does not rely on embedding search alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from services.rag_embeddings import EmbeddedChunk, Embedder, cosine_similarity
from services.rag_metadata_tagger import DEPRIORITIZE_TERMS

# FoxWatch canonical BFI driver keys (aligned with parameter manifest attributes).
CANONICAL_DRIVERS = frozenset(
    {
        "water_temperature",
        "phosphorus",
        "nitrogen",
        "discharge",
        "precipitation",
        "solar_radiation",
    }
)

ATTRIBUTE_TO_DRIVER: dict[str, str] = {
    "water_temperature": "water_temperature",
    "water_temperature_c": "water_temperature",
    "orthophosphate_dissolved": "phosphorus",
    "phosphorus_ug_l": "phosphorus",
    "phosphorus": "phosphorus",
    "nitrate_nitrite_dissolved": "nitrogen",
    "nitrogen_mg_l": "nitrogen",
    "nitrogen": "nitrogen",
    "discharge": "discharge",
    "streamflow_cfs": "discharge",
    "streamflow": "discharge",
    "precipitation": "precipitation",
    "rainfall_7day_in": "precipitation",
    "solar_radiation": "solar_radiation",
    "solar_radiation_level": "solar_radiation",
}

LABEL_TO_DRIVER: dict[str, str] = {
    "water temperature": "water_temperature",
    "phosphorus": "phosphorus",
    "orthophosphate, water, filtered": "phosphorus",
    "nitrogen": "nitrogen",
    "nitrate plus nitrite, water, filtered": "nitrogen",
    "discharge": "discharge",
    "precipitation (7-day total)": "precipitation",
    "solar radiation": "solar_radiation",
}

DRIVER_RETRIEVAL_TAGS: dict[str, tuple[str, ...]] = {
    "water_temperature": ("temperature", "cyanobacteria", "stratification", "mixing"),
    "phosphorus": ("phosphorus", "orthophosphate", "nutrients", "eutrophication", "runoff"),
    "nitrogen": ("nitrate", "nutrients", "eutrophication", "water_quality"),
    "discharge": ("discharge", "streamflow", "hydrology", "residence_time"),
    "precipitation": ("precipitation", "runoff", "hydrology", "nutrients"),
    "solar_radiation": ("sunlight", "solar_radiation", "temperature", "cyanobacteria"),
}

DRIVER_DISPLAY: dict[str, str] = {
    "water_temperature": "Elevated water temperature",
    "phosphorus": "Elevated phosphorus",
    "nitrogen": "Elevated nitrogen",
    "discharge": "Reduced discharge / low streamflow",
    "precipitation": "Recent precipitation and runoff loading",
    "solar_radiation": "Elevated solar radiation / sunlight",
}

WHO_PREFERRED_CHAPTERS = frozenset({"4", "7", "8"})
PREFERRED_SOURCE_TYPES = frozenset(
    {"who_guidance", "epa_guidance", "research_paper", "textbook_chapter"}
)

PENALTY_TERMS = DEPRIORITIZE_TERMS + (
    "public communication",
    "risk communication",
    "outreach",
    "administrative",
    "laboratory",
    "toxin monitoring",
)

VECTOR_WEIGHT = 0.50
TAG_WEIGHT = 0.30
PRIORITY_WEIGHT = 0.20
SOURCE_BOOST_MAX = 0.15
SOURCE_PENALTY_MAX = 0.20

PRIORITY_SCORE = {"high": 1.0, "medium": 0.65, "low": 0.25}


@dataclass
class DriverExtractionResult:
    """Dominant positive BFI contributors."""

    drivers: list[str]
    driver_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RankedChunk:
    """Retrieved chunk with hybrid score breakdown."""

    chunk: EmbeddedChunk
    hybrid_score: float
    vector_score: float
    tag_score: float
    priority_score: float
    source_adjustment: float
    matched_tags: list[str] = field(default_factory=list)


@dataclass
class EvidencePackage:
    """Retrieved evidence for insight generation."""

    context_summary: str
    supporting_chunks: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    ranked: list[RankedChunk] = field(default_factory=list)
    retrieval_tags: list[str] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)


def normalize_driver_key(factor: Mapping[str, Any]) -> Optional[str]:
    """Map a BFI factor row to a canonical driver key."""
    if factor.get("points", 0) <= 0:
        return None

    raw = (
        factor.get("driver")
        or factor.get("attribute")
        or factor.get("factor")
        or ""
    )
    if isinstance(raw, str):
        key = raw.strip().lower().replace(" ", "_")
        if key in CANONICAL_DRIVERS:
            return key
        if key in ATTRIBUTE_TO_DRIVER:
            return ATTRIBUTE_TO_DRIVER[key]
        if raw.strip().lower() in LABEL_TO_DRIVER:
            return LABEL_TO_DRIVER[raw.strip().lower()]

    attribute = str(factor.get("attribute", "")).strip().lower()
    if attribute in ATTRIBUTE_TO_DRIVER:
        return ATTRIBUTE_TO_DRIVER[attribute]

    label = str(factor.get("factor", "")).strip().lower()
    if label in LABEL_TO_DRIVER:
        return LABEL_TO_DRIVER[label]

    return None


def extract_dominant_drivers(bfi_result: Mapping[str, Any]) -> DriverExtractionResult:
    """
    Determine dominant environmental drivers from a BFI payload.

    Only factors with ``points > 0`` are included, sorted by descending points.
    """
    factors = bfi_result.get("factors") or []
    scored: list[tuple[str, dict[str, Any]]] = []

    for factor in factors:
        if not isinstance(factor, Mapping):
            continue
        points = int(factor.get("points") or 0)
        if points <= 0:
            continue
        driver = normalize_driver_key(factor)
        if driver is None:
            continue
        scored.append(
            (
                driver,
                {
                    "driver": driver,
                    "points": points,
                    "status": factor.get("status"),
                    "value": factor.get("value"),
                    "display": DRIVER_DISPLAY.get(driver, driver.replace("_", " ")),
                },
            )
        )

    scored.sort(key=lambda item: item[1]["points"], reverse=True)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    drivers: list[str] = []
    details: list[dict[str, Any]] = []
    for driver, detail in scored:
        if driver in seen:
            continue
        seen.add(driver)
        drivers.append(driver)
        details.append(detail)

    return DriverExtractionResult(drivers=drivers, driver_details=details)


def retrieval_tags_for_drivers(drivers: Sequence[str]) -> list[str]:
    """Expand BFI drivers to corpus tag vocabulary for tag-aware retrieval."""
    tags: list[str] = []
    seen: set[str] = set()
    for driver in drivers:
        for tag in DRIVER_RETRIEVAL_TAGS.get(driver, (driver,)):
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


def _priority_value(chunk: EmbeddedChunk) -> float:
    return PRIORITY_SCORE.get(chunk.retrieval_priority, 0.25)


def _tag_match_score(chunk_tags: Sequence[str], target_tags: Sequence[str]) -> tuple[float, list[str]]:
    if not target_tags:
        return 0.0, []
    tag_set = set(chunk_tags)
    matched = [t for t in target_tags if t in tag_set]
    if not matched:
        return 0.0, []
    return min(1.0, len(matched) / max(1, min(len(target_tags), 6))), matched


def _who_chapter_number(chapter: str) -> Optional[str]:
    if not chapter:
        return None
    match = re.search(r"\b(\d+)\b", chapter)
    return match.group(1) if match else None


def _source_adjustment(chunk: EmbeddedChunk) -> float:
    """Boost preferred guidance sources; penalize off-topic sections."""
    meta = chunk.metadata
    adjustment = 0.0
    source_type = str(meta.get("source_type", "")).lower()
    title = str(meta.get("document_title", "")).lower()
    section = str(meta.get("section", "")).lower()
    chapter = str(meta.get("chapter", ""))
    blob = f"{title} {section} {chunk.text[:400].lower()}"

    if source_type in PREFERRED_SOURCE_TYPES:
        adjustment += 0.05
    if source_type == "who_guidance":
        chapter_num = _who_chapter_number(chapter)
        if chapter_num in WHO_PREFERRED_CHAPTERS:
            adjustment += 0.10
    if source_type == "epa_guidance":
        adjustment += 0.08
    if "ecology" in title or "eutroph" in title or "cyanobacter" in title:
        adjustment += 0.04

    penalty_hits = sum(1 for term in PENALTY_TERMS if term in blob)
    if penalty_hits:
        adjustment -= min(SOURCE_PENALTY_MAX, 0.04 * penalty_hits)

    return max(-SOURCE_PENALTY_MAX, min(SOURCE_BOOST_MAX, adjustment))


def _normalize_vector_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def build_retrieval_query(bfi_result: Mapping[str, Any], drivers: Sequence[str]) -> str:
    """Construct a driver-focused semantic query (one of several retrieval signals)."""
    classification = bfi_result.get("classification", "Bloom favorability")
    driver_phrase = ", ".join(drivers[:4]) or "environmental conditions"
    return (
        f"Explain mechanisms linking {driver_phrase} to harmful algal bloom formation "
        f"and bloom favorability ({classification}). Focus on nutrients, hydrology, "
        f"temperature, and sunlight drivers."
    )


def metadata_prefilter_candidates(
    index: Sequence[EmbeddedChunk],
    target_tags: Sequence[str],
) -> list[EmbeddedChunk]:
    """
    Prefer chunks tagged for active drivers or high-priority mechanism content.

    If nothing matches tags, fall back to the full index (avoid empty retrieval).
    """
    if not target_tags:
        return list(index)

    tag_set = set(target_tags)
    matched = [c for c in index if tag_set.intersection(c.tags)]
    high_priority = [c for c in index if c.retrieval_priority == "high"]
    pool = matched or high_priority or list(index)
    return pool


def hybrid_retrieve(
    bfi_result: Mapping[str, Any],
    index: Sequence[EmbeddedChunk],
    embedder: Embedder,
    *,
    top_k: int = 5,
    candidate_pool_size: int = 40,
) -> list[RankedChunk]:
    """
    Hybrid retrieval using vector similarity, tag overlap, and retrieval priority.

    Final score =
        0.50 * vector_similarity_norm
      + 0.30 * tag_match_score
      + 0.20 * retrieval_priority_score
      + source_adjustment (bounded)
    """
    extraction = extract_dominant_drivers(bfi_result)
    drivers = extraction.drivers
    target_tags = retrieval_tags_for_drivers(drivers)
    query = build_retrieval_query(bfi_result, drivers)

    candidates = metadata_prefilter_candidates(index, target_tags)
    q_vec = embedder.embed([query])[0]

    raw_vectors = [cosine_similarity(q_vec, c.embedding) for c in candidates]
    norm_vectors = _normalize_vector_scores(raw_vectors)

    ranked: list[RankedChunk] = []
    for chunk, vec_raw, vec_norm in zip(candidates, raw_vectors, norm_vectors):
        tag_score, matched = _tag_match_score(chunk.tags, target_tags)
        priority_score = _priority_value(chunk)
        source_adj = _source_adjustment(chunk)
        hybrid = (
            VECTOR_WEIGHT * vec_norm
            + TAG_WEIGHT * tag_score
            + PRIORITY_WEIGHT * priority_score
            + source_adj
        )
        ranked.append(
            RankedChunk(
                chunk=chunk,
                hybrid_score=hybrid,
                vector_score=vec_raw,
                tag_score=tag_score,
                priority_score=priority_score,
                source_adjustment=source_adj,
                matched_tags=matched,
            )
        )

    ranked.sort(key=lambda r: r.hybrid_score, reverse=True)

    # Ensure driver coverage: reserve slots for top tag matches per primary driver.
    selected: list[RankedChunk] = []
    selected_ids: set[str] = set()

    def add(item: RankedChunk) -> None:
        if item.chunk.chunk_id in selected_ids:
            return
        selected.append(item)
        selected_ids.add(item.chunk.chunk_id)

    for driver in drivers[:3]:
        driver_tags = set(DRIVER_RETRIEVAL_TAGS.get(driver, ()))
        for item in ranked:
            if driver_tags.intersection(item.chunk.tags):
                add(item)
                break
        if len(selected) >= top_k:
            break

    for item in ranked:
        if len(selected) >= top_k:
            break
        add(item)

    return selected[:top_k]


def chunk_to_source(chunk: EmbeddedChunk) -> dict[str, Any]:
    """Citation metadata for a retrieved chunk."""
    meta = chunk.metadata
    return {
        "document_title": meta.get("document_title", ""),
        "chapter": meta.get("chapter", ""),
        "section": meta.get("section", ""),
        "authors": meta.get("authors", ""),
        "year": meta.get("year", ""),
        "chunk_id": chunk.chunk_id,
        "source_type": meta.get("source_type", ""),
    }


def build_evidence_package(
    bfi_result: Mapping[str, Any],
    index: Sequence[EmbeddedChunk],
    embedder: Embedder,
    *,
    top_k: int = 5,
) -> EvidencePackage:
    """Retrieve and assemble the evidence package for Gemini insight generation."""
    extraction = extract_dominant_drivers(bfi_result)
    ranked = hybrid_retrieve(bfi_result, index, embedder, top_k=top_k)
    tags = retrieval_tags_for_drivers(extraction.drivers)

    supporting: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for item in ranked:
        chunk = item.chunk
        supporting.append(
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "retrieval_summary": chunk.retrieval_summary,
                "tags": chunk.tags,
                "matched_tags": item.matched_tags,
                "hybrid_score": round(item.hybrid_score, 4),
                "metadata": chunk_to_source(chunk),
            }
        )
        title = str(chunk.metadata.get("document_title", ""))
        if title and title not in seen_titles:
            seen_titles.add(title)
            sources.append(chunk_to_source(chunk))

    if extraction.drivers:
        driver_text = ", ".join(extraction.drivers)
        context_summary = (
            f"Retrieved {len(ranked)} evidence sections focused on "
            f"{driver_text} for {bfi_result.get('classification', 'BFI assessment')}. "
            f"Tags prioritized: {', '.join(tags)}."
        )
    else:
        context_summary = (
            "No positive BFI driver factors were available; retrieval used general "
            "bloom-driver literature with limited driver-specific filtering."
        )

    return EvidencePackage(
        context_summary=context_summary,
        supporting_chunks=supporting,
        sources=sources,
        ranked=ranked,
        retrieval_tags=tags,
        drivers=extraction.drivers,
    )
