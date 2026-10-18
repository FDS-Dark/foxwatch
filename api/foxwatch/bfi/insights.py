"""
BFI insight prompt construction, confidence scoring, and structured outputs.

Supports Gemini prompt generation plus evidence-bound fallback synthesis for tests
and offline use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from foxwatch.bfi.retrieval import (
    DRIVER_DISPLAY,
    EvidencePackage,
    build_evidence_package,
    extract_dominant_drivers,
)
from foxwatch.bfi.gemini import (
    gemini_configured,
    generate_structured_insights,
    merge_gemini_insights,
)
from foxwatch.rag.embeddings import EmbeddedChunk, Embedder


@dataclass
class ConfidenceResult:
    level: str
    percent: int
    reason: str


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
                    f"Title: {meta.get('document_title', '')}",
                    f"Chapter: {meta.get('chapter', '')}",
                    f"Section: {meta.get('section', '')}",
                    f"Authors: {meta.get('authors', '')}",
                    f"Year: {meta.get('year', '')}",
                    f"Summary: {chunk.get('retrieval_summary', '')}",
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

Generate:

1. Executive Summary
2. Key Contributing Factors
3. Scientific Interpretation
4. Confidence Assessment
5. Sources Consulted

Instructions:
- Explain WHY bloom favorability is at its current level.
- Reference ONLY the retrieved evidence above.
- Avoid speculation and do not invent scientific claims.
- Identify which environmental factors contributed most.
- Explain relationships between factors when supported by the evidence.
- Mention uncertainty when BFI inputs or evidence are missing or limited.
- Provide source-backed scientific explanations tied to the BFI drivers.

Only use the supplied evidence.
Do not cite sources not provided.
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


def _sources_for_output(evidence: EvidencePackage) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in evidence.supporting_chunks:
        meta = chunk["metadata"]
        title = str(meta.get("document_title", ""))
        key = f"{title}|{meta.get('section', '')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "chapter": meta.get("chapter", ""),
                "section": meta.get("section", ""),
                "authors": meta.get("authors", ""),
                "year": meta.get("year", ""),
            }
        )
    return out


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

    evidence_points = [
        c.get("retrieval_summary") or c.get("text", "")[:220]
        for c in evidence.supporting_chunks[:3]
    ]
    interpretation = " ".join(evidence_points).strip()
    if not interpretation:
        interpretation = (
            "Insufficient retrieved literature was available to explain specific mechanisms "
            "for the current BFI classification."
        )

    executive = (
        f"The current assessment is {classification} ({score}/{max_score}). "
        f"Primary contributing conditions include "
        f"{', '.join(extraction.drivers) if extraction.drivers else 'limited scored drivers'}. "
        f"{evidence.context_summary}"
    )

    return {
        "executive_summary": executive,
        "bloom_assessment": (
            f"Bloom favorability is classified as {classification} based on the BFI score "
            f"of {score} out of {max_score}."
        ),
        "key_contributing_factors": key_factors,
        "scientific_interpretation": interpretation,
        "confidence": {
            "level": confidence.level,
            "percent": confidence.percent,
            "reason": confidence.reason,
        },
        "sources": _sources_for_output(evidence),
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
    prompt = build_gemini_prompt(bfi_result, evidence)
    if use_gemini and gemini_configured():
        gemini_payload, gemini_mode = generate_structured_insights(prompt)
        if gemini_payload:
            insights = merge_gemini_insights(
                insights, gemini_payload, model_tag=gemini_mode
            )
        else:
            insights["generation_mode"] = f"fallback_{gemini_mode}"

    insights["sources"] = _sources_for_output(evidence)

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
    if include_prompt:
        payload["gemini_prompt"] = prompt
    return payload


def save_insight_example(path: str, payload: Mapping[str, Any]) -> None:
    """Persist example insight payload (omit large embeddings if present)."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
