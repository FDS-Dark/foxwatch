"""
Semantic chunking for scientific RAG corpora.

Builds concept-coherent chunks from sectioned paragraphs with word-count targets
and inter-chunk overlap. Avoids mid-sentence splits.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from services.rag_document_processor import ProcessedDocument, iter_paragraphs

TARGET_MIN_WORDS = 300
TARGET_MAX_WORDS = 600
HARD_MAX_WORDS = 800
OVERLAP_MIN_WORDS = 80
OVERLAP_MAX_WORDS = 120

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ChunkRecord:
    """One retrievable unit with required metadata fields."""

    text: str
    document_title: str
    source_type: str
    chapter: str
    section: str
    authors: str
    year: Optional[int]
    chunk_id: str
    tags: list[str] = field(default_factory=list)
    retrieval_summary: str = ""
    word_count: int = 0


def word_count(text: str) -> int:
    return len(text.split())


def _sentences(text: str) -> list[str]:
    parts = SENTENCE_END.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _take_overlap_words(text: str, target: int = OVERLAP_MAX_WORDS) -> str:
    words = text.split()
    if len(words) <= target:
        return text
    tail = words[-target:]
    joined = " ".join(tail)
    # Prefer starting overlap at a sentence boundary inside the tail.
    for sep in (". ", "? ", "! "):
        idx = joined.find(sep)
        if idx != -1 and idx < len(joined) // 2:
            return joined[idx + len(sep) :]
    return joined


def _merge_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())


def _make_chunk_id(document_title: str, section: str, index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", document_title.lower()).strip("-")[:40]
    sec = re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")[:30]
    return f"{slug}__{sec}__{index:04d}__{digest}"


def _split_oversized_paragraph(para: str) -> list[str]:
    """Split long paragraphs on sentence boundaries without breaking concepts mid-sentence."""
    if word_count(para) <= HARD_MAX_WORDS:
        return [para]
    sentences = _sentences(para)
    blocks: list[str] = []
    buf: list[str] = []
    buf_words = 0
    for sent in sentences:
        sw = word_count(sent)
        if buf_words + sw > TARGET_MAX_WORDS and buf:
            blocks.append(" ".join(buf))
            buf = [sent]
            buf_words = sw
        else:
            buf.append(sent)
            buf_words += sw
    if buf:
        blocks.append(" ".join(buf))
    return blocks


def chunk_document(
    document: ProcessedDocument,
    *,
    target_min_words: int = TARGET_MIN_WORDS,
    target_max_words: int = TARGET_MAX_WORDS,
    hard_max_words: int = HARD_MAX_WORDS,
    overlap_words: int = OVERLAP_MAX_WORDS,
) -> list[ChunkRecord]:
    """
    Semantically chunk a processed document along paragraph and section boundaries.

    Accumulates paragraphs until the target word range is met, then flushes a chunk.
    Applies ``overlap_words`` (clamped to 80–120) from the previous chunk when starting
    the next chunk in the same section stream.
    """
    overlap_words = max(OVERLAP_MIN_WORDS, min(OVERLAP_MAX_WORDS, overlap_words))
    chunks: list[ChunkRecord] = []
    buffer_paras: list[str] = []
    buffer_words = 0
    chunk_index = 0
    carry_overlap = ""
    current_section = ""

    def flush(section_name: str) -> None:
        nonlocal chunk_index, buffer_paras, buffer_words, carry_overlap
        if not buffer_paras:
            return
        body = _merge_paragraphs(buffer_paras)
        if carry_overlap:
            body = f"{carry_overlap}\n\n{body}" if body else carry_overlap
        if word_count(body) < 40:
            buffer_paras = []
            buffer_words = 0
            return
        chunk_index += 1
        cid = _make_chunk_id(document.document_title, section_name, chunk_index, body)
        chunks.append(
            ChunkRecord(
                text=body,
                document_title=document.document_title,
                source_type=document.source_type,
                chapter=document.chapter or section_name,
                section=section_name,
                authors=document.authors,
                year=document.year,
                chunk_id=cid,
                word_count=word_count(body),
            )
        )
        carry_overlap = _take_overlap_words(body, overlap_words)
        buffer_paras = []
        buffer_words = 0

    paragraph_stream: Iterable[tuple[str, str, str]] = iter_paragraphs(document)

    for _chapter, section_title, para in paragraph_stream:
        if current_section and section_title != current_section and buffer_paras:
            flush(current_section)
        current_section = section_title

        for piece in _split_oversized_paragraph(para):
            pw = word_count(piece)
            if buffer_words + pw > hard_max_words and buffer_paras:
                flush(section_title)
            buffer_paras.append(piece)
            buffer_words += pw
            if buffer_words >= target_min_words:
                if buffer_words >= target_max_words or buffer_words >= hard_max_words:
                    flush(section_title)

    if buffer_paras:
        flush(current_section or "Body")

    return chunks
