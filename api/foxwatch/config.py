"""Repository paths and environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root: foxwatch/ (parent of api/)
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = REPO_ROOT / "data"
RAG_SOURCES_DIR = DATA_DIR / "rag" / "sources"
RAG_INDEX_PATH = DATA_DIR / "rag" / "index" / "embedded_chunks.jsonl"
RAG_REPORTS_DIR = DATA_DIR / "rag" / "reports"
USGS_MANIFEST_PATH = DATA_DIR / "attributes" / "usgs_parameter_manifest.csv"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Override via .env (GEMINI_MODEL). Fallbacks tried in foxwatch.bfi.gemini if the primary 404s.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_MODEL_FALLBACKS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-3.8-flash",
    "gemini-1.5-flash",
)
