"""USGS ingestion and Tiger Data observation routes."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from psycopg.errors import UndefinedTable

from foxwatch.config import REPO_ROOT
from ingestion import Collector, Settings

API_ENV = REPO_ROOT / "api" / ".env"


async def _collect_forever(collector: Collector, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(collector.poll)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=collector.settings.poll_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def observation_lifespan(app: FastAPI):
    load_dotenv(API_ENV, override=False)
    collector = Collector(Settings.from_env())
    app.state.collector = collector
    stop = asyncio.Event()
    task = None
    if collector.settings.enabled and collector.settings.database_url:
        task = asyncio.create_task(_collect_forever(collector, stop))
    try:
        yield
    finally:
        stop.set()
        if task:
            await task


def register_observation_routes(app: FastAPI) -> None:
    @app.get("/ingestion/status")
    def ingestion_status(request: Request) -> dict[str, Any]:
        return request.app.state.collector.status.copy()

    @app.post("/ingestion/poll")
    def poll_now(request: Request) -> dict[str, Any]:
        collector = request.app.state.collector
        if not collector.settings.database_url:
            raise HTTPException(503, "Set database URL in api/.env (TIGER_DATABASE_URL or TIMESCALE_SERVICE_URL)")
        try:
            return collector.poll()
        except Exception:
            raise HTTPException(
                502, "Ingestion failed; see /ingestion/status for error type"
            ) from None

    @app.get("/usgs/latest")
    def latest_usgs(request: Request) -> dict[str, Any]:
        try:
            return request.app.state.collector.latest()
        except Exception:
            raise HTTPException(502, "Unable to fetch USGS observations") from None

    @app.get("/api/observations/latest")
    def latest_stored_observations(request: Request) -> dict[str, Any]:
        collector = request.app.state.collector
        if not collector.settings.database_url:
            raise HTTPException(503, "The observation database is not configured")
        try:
            return collector.stored_latest()
        except UndefinedTable:
            raise HTTPException(
                503, "Observations are not ready; waiting for the first ingestion"
            ) from None
        except Exception:
            raise HTTPException(502, "Unable to read stored observations") from None
