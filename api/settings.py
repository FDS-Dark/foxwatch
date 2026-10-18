"""Typed application settings (APP__*) with legacy Tiger/USGS env compatibility."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = Path(__file__).resolve().parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv(API_ROOT / ".env")

LEGACY_DATABASE_ENV_KEYS = (
    "TIGER_DATABASE_URL",
    "TIMESCALE_SERVICE_URL",
    "INGEST_DATABASE_URL",
)


class PostgresDatabaseConfig(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="foxwatch")
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)
    ssl: str = Field(default="disable")
    connection_url: str = Field(default="")


class JWTConfig(BaseModel):
    secret: str = Field(default="dev-secret-change-me")
    algorithm: str = Field(default="HS256")
    audience: str | None = Field(default=None)
    issuer: str | None = Field(default=None)
    verify_signature: bool = Field(default=True)
    roles_claim: str = Field(default="roles")
    permissions_claim: str = Field(default="permissions")


class EnvironmentConfig(BaseModel):
    name: str = Field(default="dev")


class UsgsConfig(BaseModel):
    station_id: str = Field(default="USGS-040851385")
    api_key: str = Field(default="")
    poll_seconds: int = Field(default=300)
    overlap_hours: int = Field(default=6)
    enabled: bool = Field(default=True)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP__", env_nested_delimiter="__", extra="ignore"
    )

    database: PostgresDatabaseConfig = Field(default_factory=PostgresDatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    usgs: UsgsConfig = Field(default_factory=UsgsConfig)


def _legacy_database_url() -> str:
    for key in LEGACY_DATABASE_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _usgs_from_env() -> UsgsConfig:
    return UsgsConfig(
        station_id=os.getenv("USGS_STATION_ID", "USGS-040851385"),
        api_key=os.getenv("USGS_API_KEY", ""),
        poll_seconds=int(os.getenv("USGS_POLL_SECONDS", "300")),
        overlap_hours=int(os.getenv("USGS_OVERLAP_HOURS", "6")),
        enabled=os.getenv("USGS_INGESTION_ENABLED", "true").lower() == "true",
    )


config = AppConfig()
config.usgs = _usgs_from_env()


def resolved_database_url() -> str:
    legacy = _legacy_database_url()
    if legacy:
        return legacy
    if config.database.connection_url.strip():
        return config.database.connection_url.strip()
    cfg = config.database
    if cfg.username and cfg.password:
        from sqlalchemy.engine import URL

        return str(
            URL.create(
                drivername="postgresql",
                username=cfg.username,
                password=cfg.password,
                host=cfg.host,
                port=cfg.port,
                database=cfg.name,
            )
        )
    return ""


@dataclass(frozen=True)
class IngestionSettings:
    database_url: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    station: str = "USGS-040851385"
    poll_seconds: int = 300
    overlap_hours: int = 6
    enabled: bool = True

    @classmethod
    def from_env(cls) -> IngestionSettings:
        database_url = resolved_database_url()
        settings = cls(
            database_url=database_url,
            api_key=config.usgs.api_key,
            station=config.usgs.station_id,
            poll_seconds=config.usgs.poll_seconds,
            overlap_hours=config.usgs.overlap_hours,
            enabled=config.usgs.enabled,
        )
        if settings.poll_seconds < 60 or not 1 <= settings.overlap_hours <= 24:
            raise ValueError("Poll interval must be >=60 seconds; overlap must be 1-24 hours")
        return settings


DATA_DIR = REPO_ROOT / "data"
RAG_SOURCES_DIR = DATA_DIR / "rag" / "sources"
RAG_INDEX_DIR = DATA_DIR / "rag" / "index"
RAG_CHUNKS_PATH = RAG_INDEX_DIR / "chunks.jsonl"
RAG_FAISS_PATH = RAG_INDEX_DIR / "vectors.faiss"
RAG_INDEX_META_PATH = RAG_INDEX_DIR / "index_meta.json"
RAG_LEGACY_INDEX_PATH = RAG_INDEX_DIR / "embedded_chunks.jsonl"
RAG_INDEX_PATH = RAG_CHUNKS_PATH
RAG_REPORTS_DIR = DATA_DIR / "rag" / "reports"
USGS_MANIFEST_PATH = DATA_DIR / "attributes" / "usgs_parameter_manifest.csv"

RAG_VECTOR_BACKEND = os.getenv("RAG_VECTOR_BACKEND", "auto").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
GEMINI_MODEL_FALLBACKS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)


def rag_use_tiger_vectors() -> bool:
    backend = RAG_VECTOR_BACKEND
    if backend == "faiss":
        return False
    if backend == "tiger":
        return bool(resolved_database_url())
    return bool(resolved_database_url())


def rag_index_available() -> bool:
    if RAG_LEGACY_INDEX_PATH.is_file():
        return True
    if not RAG_CHUNKS_PATH.is_file():
        return False
    if rag_use_tiger_vectors():
        from services.rag_tiger_store import tiger_embeddings_ready

        if tiger_embeddings_ready():
            return True
    return RAG_FAISS_PATH.is_file()
