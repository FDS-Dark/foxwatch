import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg.errors import UndefinedTable

# Load collector settings before the insights modules load repo-root defaults.
load_dotenv(Path(__file__).with_name(".env"))

if __package__:
    from .ingestion import Collector, Settings
    from .foxwatch.routes import router as insights_router
else:
    from ingestion import Collector, Settings
    from foxwatch.routes import router as insights_router


async def collect_forever(collector, stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(collector.poll)
        except Exception:
            pass  # Collector records a sanitized error; keep retrying.
        try:
            await asyncio.wait_for(stop.wait(), timeout=collector.settings.poll_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app):
    load_dotenv(Path(__file__).with_name(".env"))
    collector = Collector(Settings.from_env())
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
            await task  # Finish the active transaction before shutting down.


app = FastAPI(title="FoxWatch API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(insights_router)


@app.get("/ingestion/status")
def ingestion_status(request: Request):
    return request.app.state.collector.status.copy()


@app.post("/ingestion/poll")
def poll_now(request: Request):
    collector = request.app.state.collector
    if not collector.settings.database_url:
        raise HTTPException(503, "Set TIGER_DATABASE_URL in api/.env first")
    try:
        return collector.poll()
    except Exception:
        raise HTTPException(502, "Ingestion failed; see /ingestion/status for error type") from None


@app.get("/usgs/latest")
def latest_usgs(request: Request):
    """Preview USGS readings and missing parameters without a database."""
    try:
        return request.app.state.collector.latest()
    except Exception:
        raise HTTPException(502, "Unable to fetch USGS observations") from None


@app.get("/api/observations/latest")
def latest_stored_observations(request: Request):
    """Current station readings from Tiger Data; never falls back to USGS."""
    collector = request.app.state.collector
    if not collector.settings.database_url:
        raise HTTPException(503, "The observation database is not configured")
    try:
        return collector.stored_latest()
    except UndefinedTable:
        raise HTTPException(503, "Observations are not ready; waiting for the first ingestion") from None
    except Exception:
        raise HTTPException(502, "Unable to read stored observations") from None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
