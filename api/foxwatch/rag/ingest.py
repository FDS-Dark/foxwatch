"""
FoxWatch production RAG corpus ingestion workflow.

Usage:
    python -m foxwatch.rag.ingest
    (with ``PYTHONPATH=api`` from the repo root)

Outputs under ``data/rag/reports/`` and ``data/rag/index/embedded_chunks.jsonl``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import RAG_INDEX_PATH, RAG_REPORTS_DIR, RAG_SOURCES_DIR, REPO_ROOT
from .document_processor import extract_pdf_text, infer_source_type
from .embeddings import (
    EmbeddedChunk,
    create_production_embedder,
    cosine_similarity,
    ingest_document,
    save_embedded_chunks,
)
from .metadata_tagger import assign_tags

SOURCES_DIR = RAG_SOURCES_DIR
INDEX_PATH = RAG_INDEX_PATH
REPORTS_DIR = RAG_REPORTS_DIR

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}

VALIDATION_QUERIES = [
    "Why does phosphorus increase bloom favorability?",
    "Why does low discharge increase bloom favorability?",
    "How does rainfall contribute to nutrient loading?",
    "Why are high temperatures associated with cyanobacterial growth?",
    "What environmental conditions favor harmful algal blooms?",
]

REQUIRED_CORPUS_KEYS = (
    "who_chapter_4",
    "who_chapter_7",
    "who_chapter_8",
    "epa_hab_guidance",
    "litchman_2023",
)


@dataclass(frozen=True)
class KnownSourceRule:
    """Filename / path matching rule for FoxWatch corpus documents."""

    key: str
    filename_patterns: tuple[str, ...]
    source_type: str
    chapter: str = ""
    document_title: str = ""
    authors: str = ""
    year: Optional[int] = None


KNOWN_SOURCE_RULES: tuple[KnownSourceRule, ...] = (
    KnownSourceRule(
        key="who_chapter_4",
        filename_patterns=(
            r"who.*chapter[-\s]*4",
            r"chapter[-\s]*4.*who",
            r"who.*\bch\s*4\b",
            r"who.*\bch4\b",
            r"cyanobacter.*chapter\s*4",
        ),
        source_type="who_guidance",
        chapter="Chapter 4",
        document_title="WHO Guidelines for Cyanobacteria in Recreational Water",
        authors="World Health Organization",
    ),
    KnownSourceRule(
        key="who_chapter_7",
        filename_patterns=(
            r"who.*chapter[-\s]*7",
            r"chapter[-\s]*7.*who",
            r"who.*\bch\s*7\b",
            r"who.*\bch7\b",
        ),
        source_type="who_guidance",
        chapter="Chapter 7",
        document_title="WHO Guidelines for Cyanobacteria in Recreational Water",
        authors="World Health Organization",
    ),
    KnownSourceRule(
        key="who_chapter_8",
        filename_patterns=(
            r"who.*chapter[-\s]*8",
            r"chapter[-\s]*8.*who",
            r"who.*\bch\s*8\b",
            r"who.*\bch8\b",
        ),
        source_type="who_guidance",
        chapter="Chapter 8",
        document_title="WHO Guidelines for Cyanobacteria in Recreational Water",
        authors="World Health Organization",
    ),
    KnownSourceRule(
        key="epa_hab_guidance",
        filename_patterns=(
            r"epa",
            r"hab.*guid",
            r"harmful.*algal.*bloom.*guid",
            r"what causes habs",
        ),
        source_type="epa_guidance",
        document_title="EPA Harmful Algal Bloom Guidance",
        authors="U.S. Environmental Protection Agency",
    ),
    KnownSourceRule(
        key="litchman_2023",
        filename_patterns=(
            r"litchman",
            r"litchman.*2023",
            r"2023.*litchman",
            r"understanding and predicting harmful algal blooms",
            r"changing climate.*hab",
        ),
        source_type="peer_reviewed_paper",
        document_title="Understanding and predicting harmful algal blooms in a changing climate",
        authors="Litchman et al.",
        year=2023,
    ),
)


@dataclass
class SourceFileRecord:
    path: str
    filename: str
    suffix: str
    size_bytes: int
    page_count: Optional[int]
    detected_title: str
    source_type: str
    chapter: str
    authors: str
    year: Optional[int]
    known_source_key: Optional[str]
    verification_status: str
    verification_notes: str = ""


@dataclass
class IngestionReport:
    generated_at_utc: str
    embedding_model: str
    source_manifest: list[SourceFileRecord] = field(default_factory=list)
    missing_required_sources: list[str] = field(default_factory=list)
    total_chunks: int = 0
    chunks_per_source: dict[str, int] = field(default_factory=dict)
    chunks_per_tag: dict[str, int] = field(default_factory=dict)
    retrieval_priority_counts: dict[str, int] = field(default_factory=dict)
    example_chunks: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    readiness: dict[str, Any] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def discover_source_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        directory.mkdir(parents=True, exist_ok=True)
        return []
    files = [
        path
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return files


def match_known_source(path: Path) -> Optional[KnownSourceRule]:
    blob = f"{path.name} {path.as_posix()}".lower()
    for rule in KNOWN_SOURCE_RULES:
        for pattern in rule.filename_patterns:
            if re.search(pattern, blob, flags=re.IGNORECASE):
                return rule
    return None


def infer_ingest_kwargs(path: Path) -> dict[str, Any]:
    """Infer FoxWatch metadata overrides for a source file."""
    rule = match_known_source(path)
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    kwargs: dict[str, Any] = {
        "document_title": title.title(),
        "source_type": infer_source_type(path),
    }
    if rule:
        kwargs.update(
            {
                "source_type": rule.source_type,
                "chapter": rule.chapter,
                "document_title": rule.document_title or kwargs["document_title"],
                "authors": rule.authors,
            }
        )
        if rule.year is not None:
            kwargs["year"] = rule.year
    return kwargs


def verify_pdf(path: Path) -> tuple[Optional[int], str, str]:
    """
    Verify a PDF and return page count, status, notes.

    Returns:
        (page_count, status, notes)
    """
    if path.suffix.lower() != ".pdf":
        return None, "skipped_non_pdf", "Not a PDF"
    try:
        pages = extract_pdf_text(path)
    except Exception as exc:
        return None, "error", f"PDF extraction failed: {exc}"
    if not pages:
        return 0, "error", "PDF has no pages"
    empty_pages = sum(1 for page in pages if not (page or "").strip())
    if empty_pages == len(pages):
        return len(pages), "warning", "All pages appear empty after text extraction"
    if empty_pages > len(pages) * 0.5:
        return len(pages), "warning", f"{empty_pages}/{len(pages)} pages empty after extraction"
    return len(pages), "ok", f"{len(pages) - empty_pages} pages with extractable text"


def build_source_manifest(files: list[Path]) -> list[SourceFileRecord]:
    records: list[SourceFileRecord] = []
    matched_keys: set[str] = set()

    for path in files:
        rule = match_known_source(path)
        if rule:
            matched_keys.add(rule.key)
        kwargs = infer_ingest_kwargs(path)
        page_count: Optional[int] = None
        status = "ok"
        notes = ""

        if path.suffix.lower() == ".pdf":
            page_count, status, notes = verify_pdf(path)

        records.append(
            SourceFileRecord(
                path=str(path.relative_to(REPO_ROOT)),
                filename=path.name,
                suffix=path.suffix.lower(),
                size_bytes=path.stat().st_size,
                page_count=page_count,
                detected_title=str(kwargs.get("document_title", path.stem)),
                source_type=str(kwargs.get("source_type", "")),
                chapter=str(kwargs.get("chapter", "")),
                authors=str(kwargs.get("authors", "")),
                year=kwargs.get("year"),
                known_source_key=rule.key if rule else None,
                verification_status=status,
                verification_notes=notes,
            )
        )

    return records


def missing_required_sources(records: list[SourceFileRecord]) -> list[str]:
    present = {r.known_source_key for r in records if r.known_source_key}
    return [key for key in REQUIRED_CORPUS_KEYS if key not in present]


def ingest_all_sources(
    files: list[Path],
    embedder: Any,
) -> tuple[list[EmbeddedChunk], dict[str, int]]:
    all_embedded: list[EmbeddedChunk] = []
    chunks_per_source: Counter[str] = Counter()

    for path in files:
        kwargs = infer_ingest_kwargs(path)
        embedded = ingest_document(path, embedder=embedder, **kwargs)
        rule = match_known_source(path)
        source_label = rule.key if rule else str(kwargs.get("document_title", path.name))
        chunks_per_source[source_label] += len(embedded)
        all_embedded.extend(embedded)

    return all_embedded, dict(chunks_per_source)


def audit_index(chunks: list[EmbeddedChunk]) -> dict[str, Any]:
    tag_counter: Counter[str] = Counter()
    priority_counter: Counter[str] = Counter()
    for chunk in chunks:
        tag_counter.update(chunk.tags)
        priority_counter[chunk.retrieval_priority] += 1

    examples = []
    for chunk in chunks[:5]:
        examples.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_title": chunk.metadata.get("document_title"),
                "chapter": chunk.metadata.get("chapter"),
                "section": chunk.metadata.get("section"),
                "source_type": chunk.metadata.get("source_type"),
                "tags": chunk.tags,
                "retrieval_priority": chunk.retrieval_priority,
                "text_preview": chunk.text[:240] + ("..." if len(chunk.text) > 240 else ""),
            }
        )

    return {
        "total_chunks": len(chunks),
        "chunks_per_tag": dict(sorted(tag_counter.items())),
        "retrieval_priority_counts": dict(priority_counter),
        "example_chunks": examples,
    }


def validate_retrieval(
    chunks: list[EmbeddedChunk],
    embedder: Any,
    queries: list[str],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for query in queries:
        query_tags = set(assign_tags(query))
        q_vec = embedder.embed([query])[0]
        scored: list[tuple[EmbeddedChunk, float, list[str]]] = []
        for chunk in chunks:
            sim = cosine_similarity(q_vec, chunk.embedding)
            matched = sorted(set(chunk.tags).intersection(query_tags))
            scored.append((chunk, sim, matched))
        scored.sort(key=lambda row: row[1], reverse=True)
        top = scored[:top_k]
        results.append(
            {
                "query": query,
                "query_tags": sorted(query_tags),
                "top_k": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "similarity_score": round(sim, 4),
                        "document_title": chunk.metadata.get("document_title"),
                        "chapter": chunk.metadata.get("chapter"),
                        "section": chunk.metadata.get("section"),
                        "source_type": chunk.metadata.get("source_type"),
                        "tags": chunk.tags,
                        "tags_matched": matched,
                        "retrieval_summary": chunk.retrieval_summary,
                        "text_preview": chunk.text[:220] + ("..." if len(chunk.text) > 220 else ""),
                    }
                    for chunk, sim, matched in top
                ],
            }
        )
    return results


def evaluate_readiness(
    *,
    files: list[Path],
    records: list[SourceFileRecord],
    chunks: list[EmbeddedChunk],
    missing_required: list[str],
    validation_results: list[dict[str, Any]],
    index_path: Path,
) -> dict[str, Any]:
    pdf_records = [r for r in records if r.suffix == ".pdf"]
    pdf_errors = [r for r in pdf_records if r.verification_status == "error"]
    metadata_ok = all(
        bool(c.metadata.get("document_title")) and "chunk_id" in c.metadata for c in chunks
    )

    required_source_types = {"who_guidance", "epa_guidance", "peer_reviewed_paper"}
    indexed_types = {c.metadata.get("source_type") for c in chunks}
    has_required_types = required_source_types.issubset(indexed_types)

    validation_hits = 0
    for result in validation_results:
        for hit in result["top_k"]:
            st = hit.get("source_type")
            title = str(hit.get("document_title", "")).lower()
            if st in required_source_types or "who" in title or "epa" in title or "litchman" in title:
                validation_hits += 1
                break

    checks = {
        "all_pdfs_verified": len(pdf_errors) == 0,
        "all_pdfs_ingested": len(pdf_records) > 0 and not missing_required,
        "required_sources_present": len(missing_required) == 0,
        "index_file_created": index_path.is_file() and index_path.stat().st_size > 0,
        "chunk_metadata_present": metadata_ok and len(chunks) > 0,
        "retrieval_returns_corpus_sources": validation_hits >= min(3, len(validation_results)),
        "indexed_required_source_types": has_required_types,
    }

    passed = all(
        [
            checks["index_file_created"],
            checks["chunk_metadata_present"],
            checks["required_sources_present"],
            checks["all_pdfs_ingested"],
            checks["retrieval_returns_corpus_sources"],
            checks["indexed_required_source_types"],
            checks["all_pdfs_verified"],
        ]
    )

    return {
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "pdf_count": len(pdf_records),
        "source_file_count": len(files),
        "missing_required_sources": missing_required,
        "indexed_source_types": sorted(indexed_types),
    }


def write_reports(report: IngestionReport) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    (REPORTS_DIR / "ingestion_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest_lines = [
        "# FoxWatch RAG Source Manifest",
        "",
        f"Generated: {report.generated_at_utc}",
        "",
        "| Filename | Title | Source type | Chapter | Pages | Status | Known key |",
        "|---|---|---|---|---:|---|---|",
    ]
    for row in report.source_manifest:
        manifest_lines.append(
            f"| {row.filename} | {row.detected_title} | {row.source_type} | "
            f"{row.chapter or '—'} | {row.page_count if row.page_count is not None else '—'} | "
            f"{row.verification_status} | {row.known_source_key or '—'} |"
        )
    (REPORTS_DIR / "source_manifest.md").write_text("\n".join(manifest_lines), encoding="utf-8")

    validation_md = ["# Retrieval Validation", ""]
    for block in report.validation_results:
        validation_md.append(f"## {block['query']}")
        validation_md.append("")
        for hit in block["top_k"]:
            validation_md.append(
                f"- **{hit['similarity_score']}** — {hit['document_title']} "
                f"({hit.get('chapter') or 'no chapter'}) "
                f"tags matched: {', '.join(hit['tags_matched']) or 'none'}"
            )
        validation_md.append("")
    (REPORTS_DIR / "retrieval_validation.md").write_text("\n".join(validation_md), encoding="utf-8")

    readiness_md = [
        "# FoxWatch RAG Readiness Report",
        "",
        f"**Status: {report.readiness.get('status', 'UNKNOWN')}**",
        "",
        "## Checks",
    ]
    for name, ok in report.readiness.get("checks", {}).items():
        readiness_md.append(f"- {'✅' if ok else '❌'} {name}")
    if report.missing_required_sources:
        readiness_md.extend(
            [
                "",
                "## Missing required sources",
                *[f"- {key}" for key in report.missing_required_sources],
            ]
        )
    (REPORTS_DIR / "readiness_report.md").write_text("\n".join(readiness_md), encoding="utf-8")


def run_workflow() -> IngestionReport:
    files = discover_source_files(SOURCES_DIR)
    manifest = build_source_manifest(files)
    missing = missing_required_sources(manifest)

    embedder = create_production_embedder()
    chunks, chunks_per_source = ingest_all_sources(files, embedder)

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_embedded_chunks(INDEX_PATH, chunks)

    audit = audit_index(chunks)
    validation = validate_retrieval(chunks, embedder, VALIDATION_QUERIES)
    readiness = evaluate_readiness(
        files=files,
        records=manifest,
        chunks=chunks,
        missing_required=missing,
        validation_results=validation,
        index_path=INDEX_PATH,
    )

    report = IngestionReport(
        generated_at_utc=_utc_now(),
        embedding_model=embedder.model_name,
        source_manifest=manifest,
        missing_required_sources=missing,
        total_chunks=audit["total_chunks"],
        chunks_per_source=chunks_per_source,
        chunks_per_tag=audit["chunks_per_tag"],
        retrieval_priority_counts=audit["retrieval_priority_counts"],
        example_chunks=audit["example_chunks"],
        validation_results=validation,
        readiness=readiness,
    )
    write_reports(report)
    return report


def main() -> None:
    report = run_workflow()
    print(json.dumps({"status": report.readiness.get("status"), "total_chunks": report.total_chunks}, indent=2))
    print(f"Index: {INDEX_PATH}")
    print(f"Reports: {REPORTS_DIR}")


if __name__ == "__main__":
    main()
