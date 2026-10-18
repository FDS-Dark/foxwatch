# FoxWatch production deployment

Production uses **Docker Hub** for container images and **DigitalOcean App Platform** to run them. Pushes to `main` build and push images in GitHub Actions, then trigger a new App Platform deployment.

## Architecture

- **foxwatch-web** — React UI (nginx serves static files inside the container)
- **foxwatch-api** — FastAPI + USGS ingestion (always-on web service)
- **Tiger Data** — USGS observations + RAG embedding vectors (pgvector)
- **GoDaddy DNS** — CNAME to App Platform for your custom domain

Chunk text ships in the API image (`data/rag/index/chunks.jsonl`). **Vectors** must exist in Tiger (`rag_chunk_vectors`).

## One-time: Docker Hub

1. Create a [Docker Hub](https://hub.docker.com/) account if needed.
2. Create **public** repositories `foxwatch-api` and `foxwatch-web` (or rely on first push to create them).
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

Push to `main` runs [`.github/workflows/publish-dockerhub.yml`](../.github/workflows/publish-dockerhub.yml).

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
docker login
docker build -f api/Dockerfile -t YOUR_DOCKERHUB_USERNAME/foxwatch-api:latest .
docker push YOUR_DOCKERHUB_USERNAME/foxwatch-api:latest
docker build -f client/Dockerfile -t YOUR_DOCKERHUB_USERNAME/foxwatch-web:latest .
docker push YOUR_DOCKERHUB_USERNAME/foxwatch-web:latest
doctl apps create-deployment YOUR_APP_ID
```
