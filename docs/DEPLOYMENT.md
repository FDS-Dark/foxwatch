# FoxWatch production deployment

Production uses **Docker Hub** for container images and **DigitalOcean App Platform** to run them. Pushes to `main` build and push images in GitHub Actions, then trigger a new App Platform deployment.

## Architecture

- **foxwatch-web** — React UI (nginx serves static files inside the container)
- **foxwatch-api** — FastAPI + USGS ingestion (always-on web service)
- **foxwatch-xray-worker** — Sentinel-2 refresh on **Vultr Cloud Compute** (Docker)
- **Vultr Object Storage** — public `live/*` map artifacts (PNG + JSON + gzipped samples)
- **Tiger Data** — USGS observations + RAG embedding vectors (pgvector)
- **GoDaddy DNS** — CNAME to App Platform for your custom domain

Chunk text ships in the API image (`data/rag/index/chunks.jsonl`). **Vectors** must exist in Tiger (`rag_chunk_vectors`).
Historical X-Ray replay exports ship in the API image (`data/xray`, excluding ephemeral `data/xray/live`).
Live map metadata and point inspection are read from `XRAY_LIVE_PUBLIC_BASE_URL`; map PNGs load directly from object storage.

## One-time: Docker Hub

1. Create a [Docker Hub](https://hub.docker.com/) account if needed.
2. Create **public** repositories `foxwatch-api`, `foxwatch-web`, and `foxwatch-xray-worker` (or rely on first push to create them).
3. Create an **Access Token** (Account Settings → Security) for CI — use this as `DOCKERHUB_TOKEN`, not your account password.

Public images are pullable by App Platform without registry credentials. Do not bake secrets into images; use App Platform env vars only.

## One-time: DigitalOcean App Platform

1. Create an **App** from [`.do/app.yaml`](../.do/app.yaml):
   - Replace `YOUR_DOCKERHUB_USERNAME` with your Hub namespace (twice).
   - Import the spec or create matching services (**Deploy from container image**, not Git).
2. Set **encrypted environment variables** on the **api** service from [`deploy/env.example`](../deploy/env.example).
3. Copy the App ID for GitHub (`DO_APP_ID`).

If you use **private** Docker Hub repos, add Docker Hub credentials under the app’s registry settings in the DO control panel.

## One-time: GitHub Actions secrets

| Secret | Purpose |
|--------|---------|
| `DOCKERHUB_USERNAME` | Docker Hub namespace (user or org) |
| `DOCKERHUB_TOKEN` | Hub access token for `docker push` |
| `DIGITALOCEAN_ACCESS_TOKEN` | DO API token (App Platform deploy only) |
| `DO_APP_ID` | App Platform application UUID |
| `VULTR_SSH_HOST` | (Optional) VPS hostname for worker redeploy |
| `VULTR_SSH_USER` | (Optional) SSH user on the VPS |
| `VULTR_SSH_KEY` | (Optional) Private key for CI `docker compose pull` |
| `VULTR_COMPOSE_DIR` | (Optional) Path to `deploy/xray-worker` on the VPS |

Push to `main` runs [`.github/workflows/publish-dockerhub.yml`](../.github/workflows/publish-dockerhub.yml).

## One-time: Vultr Object Storage

1. Create a **Vultr Object Storage** bucket in a region near Green Bay (for example `ewr1`).
2. Create **S3-compatible access keys** with write access; keep them on the worker only.
3. Enable **public read** for the published prefix (`live/`). Typical layout:
   - `live/status.json` — worker phase and last check time
   - `live/manifest.json` — pointer to the current snapshot
   - `live/{run_id}/` — immutable PNG layers, `manifest.json`, `samples.json.gz`
4. Set the bucket **CORS** policy to allow `GET` from your production site origin (map tiles load in the browser cross-origin).
5. Note the public HTTPS base URL (for example `https://your-bucket.ewr1.vultrobjects.com`) for `XRAY_LIVE_PUBLIC_BASE_URL`.

Write credentials never belong in the API image or App Platform env; only the public base URL is configured on DigitalOcean.

## One-time: Vultr Cloud Compute worker

1. Provision a small VPS (2 vCPU / 4 GB RAM is comfortable for GDAL + hourly refresh).
2. Install Docker and Docker Compose.
3. Copy [`deploy/env.vultr.example`](../deploy/env.vultr.example) to `deploy/xray-worker/.env` on the server and fill in S3 + public URL values.
4. Clone this repo (or copy only [`deploy/xray-worker/docker-compose.yml`](../deploy/xray-worker/docker-compose.yml) and `.env`).
5. Start the worker:

```bash
cd deploy/xray-worker
docker compose pull
docker compose up -d
```

The worker persists scene downloads on the `xray-live-cache` volume. Staging files under `/var/lib/xray-live` are optional; production maps are published to object storage.

First run can take several minutes while Sentinel-2 windows download. Check logs with `docker compose logs -f`.

**Rollback:** stop the worker (`docker compose down`); the last completed `live/manifest.json` in the bucket remains served until a new snapshot succeeds.

## Local X-Ray worker (development)

Without Vultr credentials, run once or with `--watch` from the research environment; artifacts stay under `data/xray/live` and the API reads them locally when `XRAY_LIVE_PUBLIC_BASE_URL` is unset:

```bash
research/xray_bay/.venv/bin/python scripts/refresh_xray_live.py --watch
```

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
docker build -f deploy/xray-worker/Dockerfile -t foxwatch-xray-worker:local .
```

Run API with env file mounted; point browser at web container only when using a reverse proxy or set `VITE_API_BASE_URL` for split testing.

## Production checklist

- [ ] `APP__environment__name=production`
- [ ] `INGESTION_ADMIN_TOKEN` set (`POST /ingestion/poll` requires `X-Ingestion-Token`)
- [ ] `APP__jwt__secret` not default dev value
- [ ] Tiger seeded with RAG vectors
- [ ] USGS ingestion running (`GET /ingestion/status`)
- [ ] Custom domain + TLS active on App Platform
- [ ] `XRAY_LIVE_PUBLIC_BASE_URL` set on the **api** service
- [ ] Vultr worker healthy (`live/status.json` `checked_at` within 2 hours)
- [ ] `GET /api/xray/live` returns `ready` or `stale` with a `map` payload

## Manual deploy

```bash
docker login
docker build -f api/Dockerfile -t YOUR_DOCKERHUB_USERNAME/foxwatch-api:latest .
docker push YOUR_DOCKERHUB_USERNAME/foxwatch-api:latest
docker build -f client/Dockerfile -t YOUR_DOCKERHUB_USERNAME/foxwatch-web:latest .
docker push YOUR_DOCKERHUB_USERNAME/foxwatch-web:latest
docker build -f deploy/xray-worker/Dockerfile -t YOUR_DOCKERHUB_USERNAME/foxwatch-xray-worker:latest .
docker push YOUR_DOCKERHUB_USERNAME/foxwatch-xray-worker:latest
doctl apps create-deployment YOUR_APP_ID
# On the Vultr VPS: cd deploy/xray-worker && docker compose pull && docker compose up -d
```
