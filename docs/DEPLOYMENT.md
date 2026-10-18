# FoxWatch production deployment

Production uses **DigitalOcean Container Registry (DOCR)** and **App Platform**. Pushes to `main` build Docker images in GitHub Actions and trigger a new App Platform deployment.

## Architecture

- **foxwatch-web** — React UI (nginx serves static files inside the container)
- **foxwatch-api** — FastAPI + USGS ingestion (always-on web service)
- **Tiger Data** — USGS observations + RAG embedding vectors (pgvector)
- **GoDaddy DNS** — CNAME to App Platform for your custom domain

Chunk text ships in the API image (`data/rag/index/chunks.jsonl`). **Vectors** must exist in Tiger (`rag_chunk_vectors`).

## One-time: DigitalOcean

1. Create a **Container Registry** (note the registry name, e.g. `foxwatch`).
2. Create an **App** from [`.do/app.yaml`](../.do/app.yaml):
   - Replace `REGISTRY_NAME` with your registry name.
   - Import the spec or create matching services manually (**Deploy from container image**, not Git).
3. Connect the app to DOCR so it can pull `foxwatch-api` and `foxwatch-web`.
4. Set **encrypted environment variables** on the **api** service from [`deploy/env.example`](../deploy/env.example).
5. Copy the App ID for GitHub (`DO_APP_ID`).

## One-time: GitHub Actions secrets

| Secret | Purpose |
|--------|---------|
| `DIGITALOCEAN_ACCESS_TOKEN` | DO API token (read/write registry + apps) |
| `DOCR_REGISTRY_NAME` | Registry name (not full URL) |
| `DO_APP_ID` | App Platform application UUID |

Push to `main` runs [`.github/workflows/publish-docr.yml`](../.github/workflows/publish-docr.yml).

## One-time: GoDaddy DNS

1. In App Platform, add your custom domain and note the target hostname.
2. In GoDaddy DNS, add a **CNAME** for `www` → App Platform hostname.
3. For apex `@`, use GoDaddy forwarding to `https://www.yourdomain` or an ALIAS record if offered.

Set `APP__public_url` and `APP__cors_origins` to match the live URLs.

## One-time: Tiger RAG seed

With `TIGER_DATABASE_URL` set locally (or run a one-off container with env):

```bash
cd api
uv sync --group rag
uv run python -m services.rag_seed
```

Or full re-ingest from sources:

```bash
uv run python -m services.rag_ingest
```

Verify: `GET /api/health` → `rag_tiger_vectors` > 0, `rag_index_present` true.

## Local Docker smoke test

From repo root:

```bash
docker build -f api/Dockerfile -t foxwatch-api:local .
docker build -f client/Dockerfile -t foxwatch-web:local .
```

Run API with env file mounted; point browser at web container only when using a reverse proxy or set `VITE_API_BASE_URL` for split testing.

## Production checklist

- [ ] `APP__environment__name=production`
- [ ] `INGESTION_ADMIN_TOKEN` set (`POST /ingestion/poll` requires `X-Ingestion-Token`)
- [ ] `APP__jwt__secret` not default dev value
- [ ] Tiger seeded with RAG vectors
- [ ] USGS ingestion running (`GET /ingestion/status`)
- [ ] Custom domain + TLS active on App Platform

## Manual deploy

```bash
doctl registry login
docker build -f api/Dockerfile -t registry.digitalocean.com/REGISTRY/foxwatch-api:latest .
docker push registry.digitalocean.com/REGISTRY/foxwatch-api:latest
# repeat for client/Dockerfile → foxwatch-web
doctl apps create-deployment YOUR_APP_ID
```
