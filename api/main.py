import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dependencies import init_collector
from settings import IngestionSettings, config, cors_allowed_origins

from routers.bfi import router as bfi_router
from routers.ingestion import router as ingestion_router
from routers.meta import router as meta_router
from routers.observations import router as observations_router
from routers.ml_review import router as ml_review_router
from routers.predictions import router as predictions_router
from routers.xray import router as xray_router


async def collect_forever(collector, stop):
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
async def lifespan(app):
    collector = init_collector(IngestionSettings.from_env())
    app.state.collector = collector
    stop = asyncio.Event()
    task = None
    if collector.settings.enabled and collector.settings.database_url:
        task = asyncio.create_task(collect_forever(collector, stop))
    try:
        yield
    finally:
        stop.set()
        if task:
            await task


app = FastAPI(
    title="FoxWatch API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if config.environment.name == "production" else "/docs",
    redoc_url=None if config.environment.name == "production" else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta_router)
app.include_router(observations_router)
app.include_router(ingestion_router)
app.include_router(predictions_router)
app.include_router(ml_review_router)
app.include_router(bfi_router)
app.include_router(xray_router)


if __name__ == "__main__":
    import os

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
