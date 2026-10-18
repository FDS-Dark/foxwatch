"""
BFI insight prompt construction, confidence scoring, and structured outputs.

Supports Gemini prompt generation plus evidence-bound fallback synthesis for tests
and offline use.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from services.bfi_retrieval import (
    DRIVER_DISPLAY,
    EvidencePackage,
    build_evidence_package,
    extract_dominant_drivers,
)
from services.gemini_client import (
    discover_external_sources,
    gemini_configured,
    generate_grounded_text,
    generate_structured_insights,
    merge_gemini_insights,
)
from services.rag_embeddings import EmbeddedChunk, Embedder, search_chunks


@dataclass
class ConfidenceResult:
    level: str
    percent: int
    reason: str


def _passage_blurb(chunk: Mapping[str, Any], *, max_len: int = 280) -> str:
    """Human-readable excerpt without repeated RAG boilerplate."""
    raw = str(chunk.get("retrieval_summary") or "").strip()
    raw = re.sub(r"^This section explains [^.]+\.\s*", "", raw, flags=re.IGNORECASE)
    if len(raw) < 48:
        raw = str(chunk.get("text") or "")[:max_len].strip()
    return raw[:max_len].strip()


def _driver_lines(bfi_result: Mapping[str, Any]) -> list[str]:
    extraction = extract_dominant_drivers(bfi_result)
    lines: list[str] = []
    for detail in extraction.driver_details:
        display = detail.get("display") or DRIVER_DISPLAY.get(
            detail["driver"], detail["driver"]
        )
        lines.append(f"- {display} ({detail['points']} points)")
    return lines


def build_gemini_prompt(
    bfi_result: Mapping[str, Any],
    evidence: EvidencePackage,
) -> str:
    """
    Build a Gemini instruction prompt grounded in BFI results and retrieved evidence.
    """
    score = bfi_result.get("score", "")
    max_score = bfi_result.get("max_possible_score", 12)
    classification = bfi_result.get("classification", "")
    driver_lines = _driver_lines(bfi_result) or ["- No positive driver factors scored"]

    evidence_blocks: list[str] = []
    for idx, chunk in enumerate(evidence.supporting_chunks, start=1):
        meta = chunk["metadata"]
        evidence_blocks.append(
            "\n".join(
                [
                    f"[Evidence {idx}]",
                    f"SourceType: {meta.get('source_type', '')}",
                    f"Title: {meta.get('document_title', '')}",
                    f"Chapter: {meta.get('chapter', '')}",
                    f"Section: {meta.get('section', '')}",
                    f"Authors: {meta.get('authors', '')}",
                    f"Year: {meta.get('year', '')}",
                    f"Summary: {_passage_blurb(chunk)}",
                    f"Text: {chunk.get('text', '')}",
                ]
            )
        )

    evidence_text = "\n\n".join(evidence_blocks) if evidence_blocks else "[No evidence retrieved]"

    return f"""Current Bloom Favorability Assessment:

Classification: {classification}
Score: {score}/{max_score}

Environmental Drivers:
{chr(10).join(driver_lines)}

Scientific Evidence:
{evidence_text}

Generate a JSON response with:

1. executive_summary — plain language for field analysts reviewing bloom favorability (no citations)
2. key_contributing_factors — bullet strings tied to BFI drivers
3. scientific_interpretation — mechanisms in plain language (no citations in this text)
4. confidence — level, percent, reason

Instructions:
- Ground all claims in the [Evidence N] blocks, but do NOT put paper titles, author names, or [Evidence N] in executive_summary or scientific_interpretation.
- Explain WHY bloom favorability is at its current level using drivers + evidence together.
- Avoid speculation; say when evidence is thin.
- Official web sources are discovered in a separate step; do not list sources in this JSON.
"""


def build_external_source_discovery_prompt(
    bfi_result: Mapping[str, Any],
    evidence: EvidencePackage,
    insights: Mapping[str, Any],
) -> str:
    """Prompt for web search — RAG included only as a consistency reference, not as citations."""
    classification = bfi_result.get("classification", "")
    score = bfi_result.get("score", "")
    max_score = bfi_result.get("max_possible_score", 12)
    driver_lines = _driver_lines(bfi_result) or ["- No positive driver factors scored"]
    summary = str(insights.get("executive_summary") or "")[:600]

    consistency_notes: list[str] = []
    for idx, chunk in enumerate(evidence.supporting_chunks, start=1):
        consistency_notes.append(f"[Ref {idx}] {_passage_blurb(chunk, max_len=200)}")

    ref_block = "\n".join(consistency_notes) if consistency_notes else "[No internal reference passages]"

    return f"""Location: Lower Fox River · Green Bay, Wisconsin (live water-quality monitoring).

Bloom favorability today: {classification} ({score}/{max_score}).
Active environmental drivers:
{chr(10).join(driver_lines)}

Analyst summary already written (keep external sources consistent with this):
{summary}

Internal research excerpts (for consistency only — do NOT cite or list as user-facing sources):
{ref_block}

Use Google Search to find 3–5 distinct official external sources (programs, guidance pages, monitoring portals)
that support or contextualize today's drivers and summary for Green Bay / Wisconsin harmful algal blooms.
"""


def compute_confidence(
    bfi_result: Mapping[str, Any],
    evidence: EvidencePackage,
) -> ConfidenceResult:
    """
    Compute confidence from BFI input coverage, retrieval relevance, and source diversity.

    Scale: 0–100 mapped to Low (0–40), Moderate (41–70), High (71–100).
    """
    factors = bfi_result.get("factors") or []
    available_inputs = len(factors)
    max_possible = int(bfi_result.get("max_possible_score") or 0)
    expected_inputs = 6
    if max_possible > 0:
        input_coverage = min(1.0, available_inputs / max(1, max_possible // 2))
    else:
        input_coverage = min(1.0, available_inputs / expected_inputs)

    retrieved = len(evidence.supporting_chunks)
    chunk_score = min(1.0, retrieved / 5.0)

    titles = {
        c["metadata"].get("document_title")
        for c in evidence.supporting_chunks
        if c.get("metadata")
    }
    diversity_score = min(1.0, len(titles) / 3.0)

    tag_hits = sum(1 for c in evidence.supporting_chunks if c.get("matched_tags"))
    tag_score = min(1.0, tag_hits / max(1, min(3, len(evidence.drivers))))

    percent = int(
        round(
            100
            * (
                0.35 * input_coverage
                + 0.30 * chunk_score
                + 0.20 * diversity_score
                + 0.15 * tag_score
            )
        )
    )
    percent = max(0, min(100, percent))

    if percent <= 40:
        level = "Low"
    elif percent <= 70:
        level = "Moderate"
    else:
        level = "High"

    reason_parts = [
        f"{available_inputs} BFI input factor(s) available",
        f"{retrieved}/5 target evidence chunks retrieved",
        f"{len(titles)} unique source document(s)",
    ]
    if evidence.drivers:
        reason_parts.append(f"driver-focused tags matched for {', '.join(evidence.drivers[:3])}")
    else:
        reason_parts.append("no positive BFI drivers limited driver-aware retrieval")

    return ConfidenceResult(
        level=level,
        percent=percent,
        reason="; ".join(reason_parts) + ".",
    )


# Official catalog used when web search is unavailable (not RAG chunk titles).
EXTERNAL_SOURCE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "EPA Harmful Algal Blooms",
        "organization": "U.S. Environmental Protection Agency",
        "url": "https://www.epa.gov/nutrientpollution/harmful-algal-blooms",
        "summary": "Federal overview of nutrient pollution and harmful algal bloom causes and response.",
        "tags": {"phosphorus", "nitrogen", "nutrients", "cyanobacteria"},
    },
    {
        "name": "USGS Water Data for the Nation",
        "organization": "U.S. Geological Survey",
        "url": "https://waterdata.usgs.gov/",
        "summary": "National portal for streamflow, nutrients, and continuous water-quality monitoring.",
        "tags": {"discharge", "streamflow", "phosphorus", "nitrogen", "water_quality"},
    },
    {
        "name": "WHO Recreational Water Quality — Cyanobacteria",
        "organization": "World Health Organization",
        "url": "https://www.who.int/teams/environment-climate-change-and-health/water-sanitation-and-health/water-quality-and-health/recreational-waters",
        "summary": "International guidance on cyanobacteria risks in recreational waters.",
        "tags": {"cyanobacteria", "water_quality", "temperature"},
    },
    {
        "name": "NOAA Harmful Algal Bloom resources",
        "organization": "NOAA National Ocean Service",
        "url": "https://oceanservice.noaa.gov/hazards/hab/",
        "summary": "Coastal and Great Lakes harmful algal bloom background and monitoring context.",
        "tags": {"cyanobacteria", "water_quality"},
    },
    {
        "name": "Wisconsin DNR Blue-Green Algae",
        "organization": "Wisconsin Department of Natural Resources",
        "url": "https://dnr.wisconsin.gov/topic/lakes/bluegreenalgae",
        "summary": "State guidance on blue-green algae recognition and public health in Wisconsin waters.",
        "tags": {"cyanobacteria", "water_quality", "phosphorus"},
    },
)

KNOWN_AUTHORITY_URLS: tuple[tuple[str, str], ...] = (
    ("world health organization", "https://www.who.int/teams/environment-climate-change-and-health/water-sanitation-and-health/water-quality-and-health/recreational-waters"),
    ("environmental protection agency", "https://www.epa.gov/nutrientpollution/harmful-algal-blooms"),
    ("u.s. geological survey", "https://water.usgs.gov/"),
    ("usgs", "https://water.usgs.gov/"),
    ("noaa", "https://oceanservice.noaa.gov/hazards/hab/"),
)


def _authority_url(organization: str) -> str:
    org = organization.lower()
    for fragment, url in KNOWN_AUTHORITY_URLS:
        if fragment in org:
            return url
    return ""


def _sanitize_analyst_summary(text: str) -> str:
    """Strip inline evidence tags and excess whitespace from analyst-facing prose."""
    cleaned = re.sub(r"\[Evidence\s+\d+\]", "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _backing_publication(chunk: Mapping[str, Any]) -> dict[str, Any]:
    meta = chunk.get("metadata") or {}
    source_type = str(meta.get("source_type", "")).lower()
    if source_type not in {"peer_reviewed_paper", "research_paper", "textbook_chapter"}:
        return {}
    title = str(meta.get("document_title", "")).strip()
    if not title:
        return {}
    return {
        "title": title,
        "authors": meta.get("authors", ""),
        "year": meta.get("year", ""),
        "section": meta.get("section", ""),
    }


def _public_source_from_chunk(index: int, chunk: Mapping[str, Any]) -> dict[str, Any]:
    meta = chunk.get("metadata") or {}
    source_type = str(meta.get("source_type", "")).lower()
    doc_title = str(meta.get("document_title", ""))
    authors = str(meta.get("authors", "")).strip()
    chapter = str(meta.get("chapter") or "").strip()
    section = str(meta.get("section") or "").strip()
    summary = _passage_blurb(chunk)

    if source_type == "epa_guidance":
        org = "U.S. Environmental Protection Agency"
        name = "EPA harmful algal bloom and nutrient pollution guidance"
    elif source_type == "who_guidance":
        org = "World Health Organization"
        if chapter:
            name = f"WHO recreational water guidance ({chapter})"
        elif section:
            name = f"WHO cyanobacteria guidance — {section[:72]}"
        else:
            name = "WHO cyanobacteria recreational water guidance"
    else:
        title_l = doc_title.lower()
        text_l = str(chunk.get("text") or "")[:600].lower()
        if "green bay" in title_l or "green bay" in text_l:
            name = "Green Bay cyanobacteria and water-quality monitoring (NOAA / regional programs)"
            org = "NOAA Great Lakes · Wisconsin water-quality programs"
        elif "litchman" in title_l or "changing climate" in title_l:
            name = "Climate change and harmful algal bloom science"
            org = "U.S. EPA · USGS research programs"
        elif "usgs" in text_l or "geological survey" in text_l:
            name = "USGS water-quality and nutrient monitoring"
            org = "U.S. Geological Survey"
        else:
            name = "Regional nutrient and cyanobacteria research programs"
            org = authors or "Peer-reviewed environmental research"

    backing = _backing_publication(chunk)
    return {
        "name": name,
        "organization": org,
        "summary": summary,
        "url": _authority_url(org),
        "evidence_indices": [index],
        "backing_publications": [backing] if backing else [],
    }


def _dedupe_backing(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(dict(item))
    return out


def _catalog_tags_for_evidence(evidence: EvidencePackage) -> set[str]:
    tags: set[str] = set(evidence.retrieval_tags or [])
    tags.update(evidence.drivers or [])
    return tags


def build_fallback_external_sources(evidence: EvidencePackage) -> list[dict[str, Any]]:
    """Curated official links when Gemini search is unavailable."""
    active = _catalog_tags_for_evidence(evidence)
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in EXTERNAL_SOURCE_CATALOG:
        overlap = len(active.intersection(row.get("tags") or set()))
        scored.append((overlap, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    picked = [dict(row, source_origin="catalog") for _, row in scored[:4]]
    if not picked:
        picked = [dict(EXTERNAL_SOURCE_CATALOG[0], source_origin="catalog")]
    for item in picked:
        item.pop("tags", None)
    return picked


def _chunk_index_for_id(chunks: Sequence[Mapping[str, Any]], chunk_id: str) -> Optional[int]:
    for i, chunk in enumerate(chunks, start=1):
        if str(chunk.get("chunk_id")) == chunk_id:
            return i
    return None


def attach_rag_consistency(
    external_sources: Sequence[Mapping[str, Any]],
    evidence: EvidencePackage,
    embedder: Embedder,
    index: Sequence[EmbeddedChunk],
    *,
    min_score: float = 0.35,
) -> list[dict[str, Any]]:
    """
    Link web/catalog sources to internal research passages for consistency checks.
    External sources remain primary; RAG is supporting only.
    """
    chunks = evidence.supporting_chunks
    if not external_sources:
        return []

    chunk_embeds: list[tuple[int, EmbeddedChunk]] = []
    id_to_idx: dict[str, int] = {}
    for i, row in enumerate(chunks, start=1):
        cid = str(row.get("chunk_id", ""))
        id_to_idx[cid] = i
        for embedded in index:
            if embedded.chunk_id == cid:
                chunk_embeds.append((i, embedded))
                break

    aligned: list[dict[str, Any]] = []
    for src in external_sources:
        row = {
            "name": str(src.get("name", "")).strip(),
            "organization": str(src.get("organization", "")).strip(),
            "summary": str(src.get("summary", "")).strip(),
            "url": str(src.get("url") or _authority_url(str(src.get("organization", "")))).strip(),
            "source_origin": str(src.get("source_origin") or "web_search"),
            "evidence_indices": [],
            "consistency": "unverified",
            "backing_publications": [],
        }
        if not row["name"]:
            continue

        query = f"{row['name']} {row['organization']} {row['summary']}"
        matches = search_chunks(query, index, embedder, top_k=5)
        indices: list[int] = []
        best_score = 0.0
        for chunk, score in matches:
            idx = _chunk_index_for_id(chunks, chunk.chunk_id)
            if idx is None:
                continue
            best_score = max(best_score, score)
            if score >= min_score and idx not in indices:
                indices.append(idx)

        if not indices and chunk_embeds:
            for idx, embedded in chunk_embeds:
                hits = search_chunks(query, [embedded], embedder, top_k=1)
                if hits and hits[0][1] >= min_score and idx not in indices:
                    indices.append(idx)
                    best_score = max(best_score, hits[0][1])

        indices = sorted(set(indices))[:2]
        row["evidence_indices"] = indices
        backing = [
            _backing_publication(chunks[idx - 1])
            for idx in indices
            if 0 < idx <= len(chunks)
        ]
        row["backing_publications"] = _dedupe_backing(backing)

        if indices and best_score >= 0.55:
            row["consistency"] = "aligned"
        elif indices:
            row["consistency"] = "partial"
        aligned.append(row)

    return aligned


def build_insight_sources(
    external_sources: Sequence[Mapping[str, Any]],
    evidence: EvidencePackage,
    embedder: Embedder,
    index: Sequence[EmbeddedChunk],
) -> list[dict[str, Any]]:
    """User-facing sources from the web/catalog, cross-checked against RAG."""
    if external_sources:
        return attach_rag_consistency(external_sources, evidence, embedder, index)
    return attach_rag_consistency(
        build_fallback_external_sources(evidence), evidence, embedder, index
    )


def finalize_public_sources(
    evidence: EvidencePackage,
    gemini_sources: Optional[Sequence[Mapping[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Backward-compatible alias — prefer build_insight_sources in new code."""
    external = list(gemini_sources or []) or build_fallback_external_sources(evidence)
    for item in external:
        if "source_origin" not in item:
            item["source_origin"] = "legacy"
    return [
        {
            "name": str(s.get("name", "")),
            "organization": str(s.get("organization", "")),
            "summary": str(s.get("summary", "")),
            "url": str(s.get("url", "")),
            "source_origin": s.get("source_origin", "legacy"),
            "evidence_indices": list(s.get("evidence_indices") or []),
            "consistency": s.get("consistency", "unverified"),
            "backing_publications": list(s.get("backing_publications") or []),
        }
        for s in external
    ]


def synthesize_insights_from_evidence(
    bfi_result: Mapping[str, Any],
    evidence: EvidencePackage,
    confidence: ConfidenceResult,
) -> dict[str, Any]:
    """
    Evidence-bound structured insight JSON without calling an LLM.

    Uses retrieved summaries and BFI drivers; suitable for tests and offline pipelines.
    """
    classification = bfi_result.get("classification", "")
    score = bfi_result.get("score", "")
    max_score = bfi_result.get("max_possible_score", 12)
    extraction = extract_dominant_drivers(bfi_result)

    key_factors = [
        detail.get("display") or detail["driver"] for detail in extraction.driver_details
    ]
    if not key_factors:
        key_factors = ["No BFI factors scored favorably in the current assessment"]

    if extraction.drivers and evidence.supporting_chunks:
        interpretation = (
            f"Recorded {', '.join(extraction.drivers[:4])} align with commonly cited "
            "nutrient, hydrology, and temperature drivers for cyanobacteria in large freshwater systems. "
            "See Sources for agency guidance and research that supports this reading."
        )
    elif evidence.supporting_chunks:
        interpretation = (
            "Retrieved guidance and research describe how nutrients, temperature, and mixing "
            "interact to influence bloom favorability. See Sources for details."
        )
    else:
        interpretation = (
            "Insufficient retrieved material was available to explain specific mechanisms "
            "for the current favorability classification."
        )

    driver_phrase = (
        ", ".join(key_factors[:5])
        if key_factors
        else "limited favorable driver signals in the current readings"
    )
    executive = (
        f"Bloom favorability is {classification} ({score} of {max_score} points). "
        f"The score mainly reflects {driver_phrase}."
    )

    return {
        "executive_summary": executive,
        "bloom_assessment": (
            f"Bloom favorability is classified as {classification} based on the BFI score "
            f"of {score} out of {max_score}."
        ),
        "key_contributing_factors": key_factors,
        "scientific_interpretation": _sanitize_analyst_summary(interpretation),
        "confidence": {
            "level": confidence.level,
            "percent": confidence.percent,
            "reason": confidence.reason,
        },
        "sources": [],
        "rag_grounded": bool(evidence.supporting_chunks),
    }


def generate_bfi_insights(
    bfi_result: Mapping[str, Any],
    index: Sequence[EmbeddedChunk],
    embedder: Embedder,
    *,
    top_k: int = 5,
    include_prompt: bool = True,
    use_gemini: bool = True,
) -> dict[str, Any]:
    """
    End-to-end insight payload: hybrid retrieval, confidence, prompt, structured JSON.
    """
    evidence = build_evidence_package(bfi_result, index, embedder, top_k=top_k)
    confidence = compute_confidence(bfi_result, evidence)
    insights = synthesize_insights_from_evidence(bfi_result, evidence, confidence)
    insights["generation_mode"] = "evidence_synthesis"

    gemini_mode = "skipped"
    source_discovery_mode = "skipped"
    external_sources: list[dict[str, Any]] = []
    prompt = build_gemini_prompt(bfi_result, evidence)
    if use_gemini and gemini_configured():
        gemini_payload, gemini_mode = generate_structured_insights(prompt)
        if gemini_payload:
            insights = merge_gemini_insights(
                insights, gemini_payload, model_tag=gemini_mode
            )
        else:
            insights["generation_mode"] = f"fallback_{gemini_mode}"

        discovery_prompt = build_external_source_discovery_prompt(
            bfi_result, evidence, insights
        )
        external_sources, source_discovery_mode = discover_external_sources(
            discovery_prompt
        )

    insights["executive_summary"] = _sanitize_analyst_summary(
        str(insights.get("executive_summary", ""))
    )
    insights["scientific_interpretation"] = _sanitize_analyst_summary(
        str(insights.get("scientific_interpretation", ""))
    )
    insights["sources"] = build_insight_sources(
        external_sources, evidence, embedder, index
    )
    if "rag_grounded" not in insights:
        insights["rag_grounded"] = bool(evidence.supporting_chunks)

    payload: dict[str, Any] = {
        "bfi": {
            "classification": bfi_result.get("classification"),
            "score": bfi_result.get("score"),
            "max_possible_score": bfi_result.get("max_possible_score"),
            "drivers": evidence.drivers,
        },
        "evidence": {
            "context_summary": evidence.context_summary,
            "supporting_chunks": evidence.supporting_chunks,
            "sources": evidence.sources,
            "retrieval_tags": evidence.retrieval_tags,
        },
        "insights": insights,
    }
    payload["gemini_status"] = gemini_mode if use_gemini else "disabled"
    payload["source_discovery_mode"] = source_discovery_mode if use_gemini else "disabled"
    if include_prompt:
        payload["gemini_prompt"] = prompt
    return payload


def _merge_question_chunks(
    evidence: EvidencePackage,
    question: str,
    index: Sequence[EmbeddedChunk],
    embedder: Embedder,
) -> list[dict[str, Any]]:
    """Driver-aware evidence plus semantic matches for the user's question."""
    by_id: dict[str, dict[str, Any]] = {
        str(c["chunk_id"]): c for c in evidence.supporting_chunks
    }
    for chunk, _score in search_chunks(question.strip(), index, embedder, top_k=4):
        if chunk.chunk_id not in by_id:
            by_id[chunk.chunk_id] = {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "retrieval_summary": chunk.retrieval_summary,
                "tags": chunk.tags,
                "matched_tags": [],
                "metadata": {
                    "document_title": chunk.metadata.get("document_title", ""),
                    "chapter": chunk.metadata.get("chapter", ""),
                    "section": chunk.metadata.get("section", ""),
                    "authors": chunk.metadata.get("authors", ""),
                    "year": chunk.metadata.get("year", ""),
                },
            }
    return list(by_id.values())[:8]


def build_bfi_ask_prompt(
    bfi_result: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    question: str,
) -> str:
    score = bfi_result.get("score", "")
    max_score = bfi_result.get("max_possible_score", 12)
    classification = bfi_result.get("classification", "")
    driver_lines = _driver_lines(bfi_result) or ["- No positive driver factors scored"]

    blocks: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        meta = chunk.get("metadata") or {}
        blocks.append(
            "\n".join(
                [
                    f"[Evidence {idx}]",
                    f"Title: {meta.get('document_title', '')}",
                    f"Section: {meta.get('section', '')}",
                    f"Summary: {chunk.get('retrieval_summary', '')}",
                    f"Text: {chunk.get('text', '')}",
                ]
            )
        )

    evidence_text = "\n\n".join(blocks) if blocks else "[No evidence retrieved]"

    return f"""Current bloom favorability (Green Bay):

Classification: {classification}
Score: {score}/{max_score}

Environmental drivers:
{chr(10).join(driver_lines)}

Retrieved research passages (semantic search):
{evidence_text}

User question:
{question.strip()}

Instructions:
- Answer the question using ONLY the evidence and BFI context above.
- Reference passages as [Evidence N].
- Do not invent studies or mechanisms not supported by the passages.
- If the question is outside the evidence, say so plainly.
"""


def answer_bfi_question(
    question: str,
    bfi_result: Mapping[str, Any],
    index: Sequence[EmbeddedChunk],
    embedder: Embedder,
    *,
    use_gemini: bool = True,
) -> dict[str, Any]:
    """Follow-up Q&A grounded in BFI state and RAG retrieval for the question."""
    q = question.strip()
    if not q:
        raise ValueError("question is required")

    evidence = build_evidence_package(bfi_result, index, embedder, top_k=5)
    chunks = _merge_question_chunks(evidence, q, index, embedder)
    prompt = build_bfi_ask_prompt(bfi_result, chunks, q)

    limitations = [
        "Answers use retrieved literature passages and current BFI inputs—not a field survey or bloom advisory.",
    ]
    mode = "evidence_synthesis"
    answer = ""

    if use_gemini and gemini_configured():
        text, mode = generate_grounded_text(prompt)
        if text:
            answer = text
        else:
            mode = f"fallback_{mode}"
            limitations.append("AI summary unavailable; showing passage-based fallback.")

    if not answer:
        snippets = [
            (c.get("retrieval_summary") or c.get("text", "")[:240]).strip()
            for c in chunks[:3]
        ]
        answer = (
            f"For “{q}”: "
            + (
                " ".join(snippets)
                if snippets
                else "No matching research passages were retrieved for this question."
            )
        )

    return {
        "question": q,
        "answer": answer,
        "generation_mode": mode,
        "limitations": limitations,
        "supporting_chunks": chunks,
        "bfi": {
            "classification": bfi_result.get("classification"),
            "score": bfi_result.get("score"),
            "max_possible_score": bfi_result.get("max_possible_score"),
        },
    }


def save_insight_example(path: str, payload: Mapping[str, Any]) -> None:
    """Persist example insight payload (omit large embeddings if present)."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
