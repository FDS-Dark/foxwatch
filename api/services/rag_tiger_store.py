"""Store RAG embedding vectors in Tiger Cloud / Timescale (PostgreSQL + pgvector)."""

from __future__ import annotations

import logging
import math
from typing import Sequence

import psycopg
from pgvector.psycopg import register_vector

from settings import resolved_database_url

LOGGER = logging.getLogger(__name__)

_META_ID = 1


def tiger_database_url() -> str:
    return resolved_database_url()


def _vector_to_list(vec: object) -> list[float]:
    to_list = getattr(vec, "to_list", None)
    if callable(to_list):
        return [float(x) for x in to_list()]
    if isinstance(vec, (list, tuple)):
        return [float(x) for x in vec]
    to_numpy = getattr(vec, "to_numpy", None)
    if callable(to_numpy):
        return [float(x) for x in to_numpy().tolist()]
    return [float(x) for x in vec]  # type: ignore[union-attr]


def _normalize(embedding: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(float(x) * float(x) for x in embedding))
    if norm == 0:
        return [float(x) for x in embedding]
    return [float(x) / norm for x in embedding]


def _connect() -> psycopg.Connection:
    url = tiger_database_url()
    if not url:
        raise RuntimeError(
            "Set TIGER_DATABASE_URL, INGEST_DATABASE_URL, or TIMESCALE_SERVICE_URL in api/.env"
        )
    conn = psycopg.connect(url, connect_timeout=15, options="-c statement_timeout=120000")
    with conn.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def _ensure_schema(cursor: psycopg.Cursor, dimension: int) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_vector_meta (
            id INT PRIMARY KEY CHECK (id = 1),
            dimension INT NOT NULL,
            chunk_count INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cursor.execute("SELECT dimension FROM rag_vector_meta WHERE id = %s", (_META_ID,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS rag_chunk_vectors (
                chunk_id TEXT PRIMARY KEY,
                sort_ord INT NOT NULL,
                embedding vector({int(dimension)}) NOT NULL
            )
            """
        )
        cursor.execute(
            "INSERT INTO rag_vector_meta (id, dimension, chunk_count) VALUES (%s, %s, 0)",
            (_META_ID, dimension),
        )
        return
    stored_dim = int(row[0])
    if stored_dim != dimension:
        raise ValueError(
            f"RAG embedding dimension is {dimension}, but Tiger index has {stored_dim}. "
            "Re-ingest or drop rag_chunk_vectors / rag_vector_meta to rebuild."
        )


def tiger_embeddings_ready() -> bool:
    if not tiger_database_url():
        return False
    try:
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'rag_chunk_vectors'
                    """
                )
                if cursor.fetchone() is None:
                    return False
                cursor.execute("SELECT 1 FROM rag_chunk_vectors LIMIT 1")
                return cursor.fetchone() is not None
    except Exception as exc:
        LOGGER.warning("Tiger RAG vector check failed: %s", type(exc).__name__)
        return False


def tiger_embedding_count() -> int:
    if not tiger_database_url():
        return 0
    try:
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'rag_chunk_vectors'
                    """
                )
                if cursor.fetchone() is None:
                    return 0
                cursor.execute("SELECT COUNT(*) FROM rag_chunk_vectors")
                row = cursor.fetchone()
                return int(row[0]) if row else 0
    except Exception:
        return 0


def save_embeddings_to_tiger(
    chunk_ids: Sequence[str],
    embeddings: Sequence[Sequence[float]],
) -> None:
    if len(chunk_ids) != len(embeddings):
        raise ValueError("chunk_ids and embeddings length mismatch")
    if not chunk_ids:
        raise ValueError("Cannot save an empty embedding index to Tiger")

    dimension = len(embeddings[0])
    rows = [
        (chunk_id, idx, _normalize(vec))
        for idx, (chunk_id, vec) in enumerate(zip(chunk_ids, embeddings))
    ]

    with _connect() as conn:
        with conn.cursor() as cursor:
            _ensure_schema(cursor, dimension)
            cursor.execute("TRUNCATE rag_chunk_vectors")
            cursor.executemany(
                """
                INSERT INTO rag_chunk_vectors (chunk_id, sort_ord, embedding)
                VALUES (%s, %s, %s)
                """,
                rows,
            )
            cursor.execute(
                """
                UPDATE rag_vector_meta
                SET chunk_count = %s, updated_at = now()
                WHERE id = %s
                """,
                (len(rows), _META_ID),
            )
        conn.commit()


def load_embeddings_from_tiger() -> dict[str, list[float]]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, embedding
                FROM rag_chunk_vectors
                ORDER BY sort_ord
                """
            )
            fetched = cursor.fetchall()
    return {str(chunk_id): _vector_to_list(vec) for chunk_id, vec in fetched}
