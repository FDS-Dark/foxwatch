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

from settings import rag_use_tiger_vectors
from services import rag_tiger_store as tiger_store
from services.rag_chunker import ChunkRecord, chunk_document
from services.rag_document_processor import process_document
from services.rag_metadata_tagger import TaggedChunk, tag_chunks


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


def _index_paths(path: Path | str) -> tuple[Path, Path, Path]:
    """Resolve chunks JSONL, FAISS index, and meta paths from ingest path."""
    out = Path(path)
    index_dir = out.parent
    chunks_path = out if out.name == "chunks.jsonl" else index_dir / "chunks.jsonl"
    return chunks_path, index_dir / "vectors.faiss", index_dir / "index_meta.json"


def _chunk_metadata_row(chunk: EmbeddedChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "metadata": chunk.metadata,
        "retrieval_summary": chunk.retrieval_summary,
        "tags": chunk.tags,
        "retrieval_priority": chunk.retrieval_priority,
    }


def _write_index_meta(
    meta_path: Path,
    *,
    vector_store: str,
    dimension: int,
    chunks: Sequence[EmbeddedChunk],
) -> None:
    meta_path.write_text(
        json.dumps(
            {
                "vector_store": vector_store,
                "format": "faiss_flat_ip" if vector_store == "faiss" else "pgvector",
                "dimension": dimension,
                "count": len(chunks),
                "chunk_ids": [chunk.chunk_id for chunk in chunks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _save_vectors_faiss(faiss_path: Path, chunks: Sequence[EmbeddedChunk]) -> int:
    import faiss
    import numpy as np

    vectors = np.asarray([chunk.embedding for chunk in chunks], dtype=np.float32)
    faiss.normalize_L2(vectors)
    dimension = int(vectors.shape[1])
    index = faiss.IndexFlatIP(dimension)
    index.add(vectors)
    faiss.write_index(index, str(faiss_path))
    return dimension


def save_embedded_chunks(path: Path | str, chunks: Sequence[EmbeddedChunk]) -> None:
    """
    Persist chunk text/metadata as JSONL and vectors in Tiger (pgvector) or FAISS.

    When ``api/.env`` defines a Tiger/Timescale URL and ``RAG_VECTOR_BACKEND`` is
    ``auto`` or ``tiger``, embeddings go to PostgreSQL; otherwise FAISS on disk.
    """
    if not chunks:
        raise ValueError("Cannot save an empty chunk index")

    chunks_path, faiss_path, meta_path = _index_paths(path)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)

    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(_chunk_metadata_row(chunk), ensure_ascii=False) + "\n")

    dimension = len(chunks[0].embedding)
    use_tiger = rag_use_tiger_vectors()
    if use_tiger:
        tiger_store.save_embeddings_to_tiger(
            [chunk.chunk_id for chunk in chunks],
            [chunk.embedding for chunk in chunks],
        )
        _write_index_meta(meta_path, vector_store="tiger", dimension=dimension, chunks=chunks)
        return

    dimension = _save_vectors_faiss(faiss_path, chunks)
    _write_index_meta(meta_path, vector_store="faiss", dimension=dimension, chunks=chunks)


def _load_legacy_jsonl(path: Path) -> list[EmbeddedChunk]:
    items: list[EmbeddedChunk] = []
    with path.open(encoding="utf-8") as handle:
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


def _load_faiss_index(chunks_path: Path, faiss_path: Path) -> list[EmbeddedChunk]:
    import faiss

    index = faiss.read_index(str(faiss_path))
    if index.ntotal == 0:
        return []

    rows: list[dict[str, Any]] = []
    with chunks_path.open(encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))

    if len(rows) != index.ntotal:
        raise ValueError(
            f"Chunk count ({len(rows)}) does not match FAISS vectors ({index.ntotal})"
        )

    items: list[EmbeddedChunk] = []
    for i, row in enumerate(rows):
        vector = index.reconstruct(int(i))
        items.append(
            EmbeddedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                embedding=vector.tolist(),
                metadata=row["metadata"],
                retrieval_summary=row["retrieval_summary"],
                tags=row["tags"],
                retrieval_priority=row["retrieval_priority"],
            )
        )
    return items


def _read_index_meta(meta_path: Path) -> dict[str, Any]:
    if not meta_path.is_file():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _load_chunks_jsonl_with_vectors(
    chunks_path: Path,
    vectors_by_id: dict[str, list[float]],
) -> list[EmbeddedChunk]:
    items: list[EmbeddedChunk] = []
    with chunks_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            chunk_id = row["chunk_id"]
            embedding = vectors_by_id.get(chunk_id)
            if embedding is None:
                raise ValueError(f"Missing embedding for chunk_id={chunk_id!r}")
            items.append(
                EmbeddedChunk(
                    chunk_id=chunk_id,
                    text=row["text"],
                    embedding=embedding,
                    metadata=row["metadata"],
                    retrieval_summary=row["retrieval_summary"],
                    tags=row["tags"],
                    retrieval_priority=row["retrieval_priority"],
                )
            )
    return items


def load_embedded_chunks(path: Path | str) -> list[EmbeddedChunk]:
    """
    Load embedded chunks from Tiger + ``chunks.jsonl``, FAISS + JSONL, or legacy JSONL.
    """
    requested = Path(path)
    chunks_path, faiss_path, meta_path = _index_paths(requested)
    meta = _read_index_meta(meta_path)
    vector_store = meta.get("vector_store")

    if chunks_path.is_file():
        prefer_tiger = vector_store == "tiger" or (
            vector_store is None and rag_use_tiger_vectors() and tiger_store.tiger_embeddings_ready()
        )
        if prefer_tiger:
            vectors = tiger_store.load_embeddings_from_tiger()
            return _load_chunks_jsonl_with_vectors(chunks_path, vectors)
        if faiss_path.is_file():
            return _load_faiss_index(chunks_path, faiss_path)

    legacy = requested
    if requested.name == "chunks.jsonl":
        legacy = requested.parent / "embedded_chunks.jsonl"
    if legacy.is_file() and legacy.name == "embedded_chunks.jsonl":
        return _load_legacy_jsonl(legacy)

    if requested.is_file():
        return _load_legacy_jsonl(requested)

    raise FileNotFoundError(
        f"RAG index not found (expected {chunks_path} + {faiss_path}, "
        f"or legacy embedded_chunks.jsonl)"
    )


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
