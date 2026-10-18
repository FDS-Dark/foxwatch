# database

PostgreSQL schema and migrations for FoxWatch (Timescale hypertables for USGS
observations). Local dev uses Docker Compose and the shared **db-upgrader**
tool; production Tiger Cloud can rely on the same tracked scripts or the
collector’s idempotent bootstrap on first poll.

## Layout

- `compose.yaml` — local TimescaleDB + migration runner
- `docker/pg_hba.conf` — pg_hba for the local postgres container
- `scripts/tracked/` — journaled structural migrations (run in order)
- `scripts/functions/` — stored functions (always re-run, not journaled)
- `scripts/untracked/` — idempotent grants/seeds
- `appsettings.json.example` — db-upgrader configuration
- `fetch-db-upgrader.sh` — downloads the db-upgrader binary from GitLab

## First start

1. Copy `.env.example` to `.env` and `appsettings.json.example` to
   `appsettings.json`, then align host/port/db/user/password with `api/.env`
   (`APP__DATABASE__*` or `TIGER_DATABASE_URL`).
2. Start Postgres and run migrations:
   ```powershell
   cd database
   $env:DB_UPGRADER_VERSION = "v0.2.0"
   docker compose up -d
   ```
3. Point the API at the same database and run `uv run uvicorn main:app --reload`
   from `api/`.

### Manual migrations (without Docker)

```powershell
$env:DB_UPGRADER_VERSION = "v0.2.0"
Copy-Item appsettings.json.example appsettings.json
$upgrader = bash ./fetch-db-upgrader.sh
& $upgrader
```

Authentication for the private db-upgrader image uses `docker login registry.gitlab.com`.
