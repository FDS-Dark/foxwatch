# FoxWatch

**HackGB 2026 · Environment & Sustainability**

FoxWatch helps investigate water-quality signals in the Lower Fox River and Green Bay by combining live USGS gauge readings, satellite-informed maps (X-Ray the Bay), and evidence-backed summaries. The product prioritizes **inspectable evidence** over black-box alerts: users can see what was measured, what changed, and what the system does not know.

> **Design principle:** Evidence first. Satellite proxies, favorability scores, and AI-assisted text are supporting context—not confirmed harmful algal bloom diagnoses or toxin measurements.

## HackGB sponsor integrations

FoxWatch is built on several HackGB sponsor tracks. Each integration supports a concrete part of the app.

| Sponsor | How we use it |
|---------|----------------|
| **[DigitalOcean](https://www.digitalocean.com/)** | **App Platform** runs production **foxwatch-web** (React/nginx) and **foxwatch-api** (FastAPI + continuous USGS ingestion). Deployments are driven from container images via [`.do/app.yaml`](.do/app.yaml) and [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). |
| **[Vultr](https://www.vultr.com/)** | **Cloud Compute** hosts the **foxwatch-xray-worker** Docker service (Sentinel-2 download, masking, live map generation). **Vultr Object Storage** publishes public `live/*` snapshots (PNG layers, manifests, sample grids) that the API and browser load through `XRAY_LIVE_PUBLIC_BASE_URL`. See [`deploy/xray-worker/`](deploy/xray-worker/). |
| **[GoDaddy](https://www.godaddy.com/)** | **DNS** for our production domain: a **CNAME** to DigitalOcean App Platform so the public demo is reachable on foxwatch.surf. |
| **[Google Gemini](https://ai.google.dev/)** | **Generative API** (optional `GEMINI_API_KEY`) for evidence-grounded narratives: Bloom Favorability Index insights and **Explain this location** on live X-Ray maps. Answers are constrained to server-retrieved evidence with citation validation and non-generative fallbacks. |
| **[Tiger Data](https://www.tigerdata.com/)** | **Managed PostgreSQL / TimescaleDB** stores the USGS observation hypertable, ingestion checkpoints, and **pgvector** RAG embedding tables (`rag_chunk_vectors`) for BFI literature retrieval in production. |

Local setup is in [`api/README.md`](api/README.md); wiring the full sponsor stack for production is in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## What’s in this repository

| Area | Description |
|------|-------------|
| [`client/`](client/) | React + Leaflet UI (current conditions, BFI insights, X-Ray replay and live maps) |
| [`api/`](api/) | FastAPI backend, USGS ingestion, BFI/RAG, X-Ray exports and live metadata |
| [`deploy/`](deploy/) | Docker Compose and env templates (API, web, Vultr x-ray worker) |
| [`docs/`](docs/) | Design notes and [production deployment](docs/DEPLOYMENT.md) |
| [`research/xray_bay/`](research/xray_bay/) | Standalone FLAMe / Sentinel-2 research that feeds portable `data/xray` exports |
| [`data/`](data/) | RAG corpus index, X-Ray artifacts, training CSVs (see `.gitignore` for large caches) |

## Quick start

1. **API** — see [`api/README.md`](api/README.md) for `uv sync`, Tiger/Timescale URL, RAG index build, and local port 8000.
2. **UI** — from `client/`: `bun install` and `bun run dev` (proxies `/api` to the API on port 8000; UI at `http://127.0.0.1:6173`).
3. **Production** — Docker Hub + DigitalOcean App Platform + Vultr worker; see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Primary data sources

- [USGS Water Data OGC API](https://api.waterdata.usgs.gov/docs/ogcapi/) — continuous observations (Fox River at Green Bay, `USGS-040851385`)
- Sentinel-2 L2A reflectance — X-Ray maps and live worker (see research docs and export scripts)
- Curated PDFs under `data/rag/sources/` — BFI literature retrieval (WHO, regional studies, etc.)
- FLAMe / field survey artifacts — X-Ray holdout and replay experiments (`research/xray_bay/`)

Attribution and retrieval details for map boundaries and evidence bundles are stored alongside exports (for example `data/xray/green_bay_boundary.geojson` and `/api/xray/evidence`).

## AI disclosure

This section satisfies HackGB participant requirements for AI and tool transparency.

### Development (code and docs)

Team members used **AI-assisted development tools** (including **Cursor** and comparable IDE assistants) during HackGB 2026 for implementation help, debugging, documentation drafts, and refactors. Architectural choices, scientific claims in the UI, dataset selection, and what ships in the demo were made and reviewed by the team. Generated suggestions were edited or rejected when they did not match project constraints.

### Runtime features (what end users may see)

| Tool / model | Role in FoxWatch |
|--------------|------------------|
| **Google Gemini** (`GEMINI_API_KEY`, optional) | Narrative synthesis for **BFI insights** (`POST /api/v1/bfi/insights`) and **Explain this location** on live X-Ray maps (`POST /api/xray/live/{run_id}/explain`). Prompts include retrieved evidence; invalid citations trigger deterministic fallbacks. |
| **BAAI/bge-small-en-v1.5** (sentence-transformers, offline) | Embeddings for RAG chunk retrieval—not user-facing generative text. |
| **Hash embedder** (deterministic) | Local/test fallback when production embeddings are unavailable. |

When Gemini is disabled, misconfigured, or fails validation, the API returns **evidence-bound fallback text** rather than unconstrained model output.

### Not powered by generative AI at request time

- USGS polling and storage, logistic-regression bloom **probability** endpoint (trained offline on `data/labeled_openai.csv`), X-Ray **random forest** grids, satellite download/masking, and map PNG generation use conventional code and statistical/ML models.
- The filename `labeled_openai.csv` refers to the training table used for the v2 classifier; it is not an OpenAI API dependency at runtime.

### How to use results responsibly

- Treat Gemini prose as **draft interpretation**; follow citations to underlying observations, literature chunks, and packaged research records.
- RFU maps, favorability indices, and probability scores are **research and demo artifacts**, not calibrated public-health or regulatory products.
- The app explicitly surfaces limitations (delayed data, seasonal transfer on live maps, missing nutrients, extrapolation hatching).

For API-level behavior and endpoints, see [`api/README.md`](api/README.md).

## Further reading

- [`docs/FoxWatch_Design_Doc_v3_Foundations.md`](docs/FoxWatch_Design_Doc_v3_Foundations.md) — product scope and constraints
- [`api/README.md`](api/README.md) — backend layout, ingestion, BFI, X-Ray live worker
- [`research/xray_bay/README.md`](research/xray_bay/README.md) — Phase 1 spatial reconstruction research
