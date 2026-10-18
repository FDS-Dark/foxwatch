"""
Seed Tiger pgvector RAG store from an on-disk index (legacy JSONL or chunks + FAISS).

Usage (from api/):
    uv run python -m services.rag_seed
    uv run python -m services.rag_seed --source data/rag/index/embedded_chunks.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

from settings import RAG_INDEX_PATH, RAG_LEGACY_INDEX_PATH, rag_use_tiger_vectors, resolved_database_url
from services.rag_embeddings import load_embedded_chunks, save_embedded_chunks


def seed(source: Path | None = None) -> int:
    if not resolved_database_url():
        raise RuntimeError("Set TIGER_DATABASE_URL (or TIMESCALE_SERVICE_URL) before seeding Tiger vectors")
    if not rag_use_tiger_vectors():
        raise RuntimeError("RAG_VECTOR_BACKEND must allow Tiger (default auto, or RAG_VECTOR_BACKEND=tiger)")

    path = source or RAG_INDEX_PATH
    if not path.is_file():
        path = RAG_LEGACY_INDEX_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"No RAG index at {RAG_INDEX_PATH} or {RAG_LEGACY_INDEX_PATH}; run services.rag_ingest first"
        )

    chunks = load_embedded_chunks(path)
    save_embedded_chunks(RAG_INDEX_PATH, chunks)
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload RAG embeddings to Tiger (pgvector)")
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Legacy embedded_chunks.jsonl or index path (default: data/rag/index/chunks.jsonl)",
    )
    args = parser.parse_args()
    count = seed(args.source)
    print(f"Seeded {count} embeddings to Tiger; chunk metadata at {RAG_INDEX_PATH}")


if __name__ == "__main__":
    main()
