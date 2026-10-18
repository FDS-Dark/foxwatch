"""
Embed tagged scientific chunks and persist them for RAG retrieval.

Uses a pluggable embedder (deterministic hash embedding for tests; optional
sentence-transformers for production).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from foxwatch.rag.chunker import ChunkRecord, chunk_document
from foxwatch.rag.document_processor import process_document
from foxwatch.rag.metadata_tagger import TaggedChunk, tag_chunks


class Embedder(Protocol):
    """Embedding backend."""

    @property
    def model_name(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbedder:
    """
    Lightweight deterministic embedder for unit tests and offline demos.

    Not suitable for production semantic search.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    @property
    def model_name(self) -> str:
        return f"hash-{self.dimensions}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import hashlib

        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [b / 255.0 for b in digest]
            vec = (raw * ((self.dimensions // len(raw)) + 1))[: self.dimensions]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


PRODUCTION_EMBEDDING_MODELS = (
    "BAAI/bge-small-en-v1.5",
    "all-MiniLM-L6-v2",
)


def create_production_embedder(
    preferred_models: Sequence[str] = PRODUCTION_EMBEDDING_MODELS,
) -> "SentenceTransformerEmbedder":
    """
    Load the first available sentence-transformers model from ``preferred_models``.

    Raises:
        ImportError: If sentence-transformers is not installed.
        RuntimeError: If no model could be loaded.
    """
    errors: list[str] = []
    for model_name in preferred_models:
        try:
            return SentenceTransformerEmbedder(model_name=model_name)
        except Exception as exc:  # pragma: no cover - model download/runtime
            errors.append(f"{model_name}: {exc}")
    raise RuntimeError(
        "Unable to load a production embedding model. Attempts: "
        + "; ".join(errors)
    )


class SentenceTransformerEmbedder:
    """Optional sentence-transformers backend."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Install sentence-transformers for production embeddings: "
                "pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(model_name)
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in vectors]


@dataclass
class EmbeddedChunk:
    """Stored vector object for retrieval."""

    chunk_id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any]
    retrieval_summary: str
    tags: list[str]
    retrieval_priority: str


def _chunk_to_metadata(chunk: ChunkRecord) -> dict[str, Any]:
    return {
        "document_title": chunk.document_title,
        "source_type": chunk.source_type,
        "chapter": chunk.chapter,
        "section": chunk.section,
        "authors": chunk.authors,
        "year": chunk.year if chunk.year is not None else "",
        "chunk_id": chunk.chunk_id,
        "word_count": chunk.word_count,
    }


def embed_tagged_chunks(
    tagged: Sequence[TaggedChunk],
    embedder: Embedder,
) -> list[EmbeddedChunk]:
    """
    Embed chunk text prefixed with retrieval summary for richer vectors.
    """
    texts = [
        f"{item.retrieval_summary}\n\n{item.chunk.text}" for item in tagged
    ]
    vectors = embedder.embed(texts)
    embedded: list[EmbeddedChunk] = []
    for item, vector in zip(tagged, vectors):
        embedded.append(
            EmbeddedChunk(
                chunk_id=item.chunk.chunk_id,
                text=item.chunk.text,
                embedding=vector,
                metadata=_chunk_to_metadata(item.chunk),
                retrieval_summary=item.retrieval_summary,
                tags=item.tags,
                retrieval_priority=item.retrieval_priority,
            )
        )
    return embedded


def ingest_directory(
    directory: Path | str,
    embedder: Optional[Embedder] = None,
    *,
    patterns: tuple[str, ...] = ("*.pdf", "*.txt", "*.md"),
) -> list[EmbeddedChunk]:
    """Ingest all supported documents under ``directory`` (e.g. ``data/rag/sources``)."""
    root = Path(directory)
    embedder = embedder or HashEmbedder()
    all_chunks: list[EmbeddedChunk] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            all_chunks.extend(ingest_document(path, embedder=embedder))
    return all_chunks


def ingest_document(
    path: Path | str,
    embedder: Optional[Embedder] = None,
    **process_kwargs: Any,
) -> list[EmbeddedChunk]:
    """
    Full pipeline: process → chunk → tag → embed one document.
    """
    embedder = embedder or HashEmbedder()
    document = process_document(path, **process_kwargs)
    chunks = chunk_document(document)
    tagged = tag_chunks(chunks)
    return embed_tagged_chunks(tagged, embedder)


def save_embedded_chunks(path: Path | str, chunks: Sequence[EmbeddedChunk]) -> None:
    """Write embedded chunks as JSON Lines."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            row = {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "embedding": chunk.embedding,
                "metadata": chunk.metadata,
                "retrieval_summary": chunk.retrieval_summary,
                "tags": chunk.tags,
                "retrieval_priority": chunk.retrieval_priority,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_embedded_chunks(path: Path | str) -> list[EmbeddedChunk]:
    """Load embedded chunks from JSON Lines."""
    items: list[EmbeddedChunk] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            items.append(
                EmbeddedChunk(
                    chunk_id=row["chunk_id"],
                    text=row["text"],
                    embedding=row["embedding"],
                    metadata=row["metadata"],
                    retrieval_summary=row["retrieval_summary"],
                    tags=row["tags"],
                    retrieval_priority=row["retrieval_priority"],
                )
            )
    return items


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search_chunks(
    query: str,
    index: Sequence[EmbeddedChunk],
    embedder: Embedder,
    *,
    top_k: int = 5,
    min_priority: Optional[str] = None,
) -> list[tuple[EmbeddedChunk, float]]:
    """
    Vector search over embedded chunks with optional retrieval-priority filter.

    ``min_priority='medium'`` drops ``low`` priority chunks (e.g. toxicology-heavy).
    """
    priority_rank = {"high": 3, "medium": 2, "low": 1}
    min_rank = priority_rank.get(min_priority or "low", 1)

    candidates = [
        c for c in index if priority_rank.get(c.retrieval_priority, 1) >= min_rank
    ]
    q_vec = embedder.embed([query])[0]
    scored = [(chunk, cosine_similarity(q_vec, chunk.embedding)) for chunk in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]
