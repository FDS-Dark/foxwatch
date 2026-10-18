# FoxWatch API

Collects USGS continuous measurements for Fox River at Green Bay, station
`USGS-040851385`, into a Tiger Data (TimescaleDB/PostgreSQL) hypertable.

## Run

From the repository root:

```powershell
cd api
uv sync
Copy-Item .env.example .env
# Edit .env: set TIGER_DATABASE_URL to your Tiger Cloud service connection URL.
uv run python main.py
```

This single process serves **Current conditions** (`GET /api/observations/latest`) and
**BFI insights** (`POST /api/v1/bfi/insights`). Equivalent from `api/`:
`uv run uvicorn foxwatch.main:app --reload --host 127.0.0.1 --port 8000`.
Repo-root `.env` holds `GEMINI_API_KEY`; `api/.env` holds the Tiger/Timescale URL.

Copy the PostgreSQL connection URL from your Tiger Cloud service's connection
details, including its port, database, password and `sslmode=require`. Keep it in
the ignored `.env` file. The database must have TimescaleDB enabled and the user
must have permission to create tables and hypertables. The collector creates
`usgs_observations` and `usgs_ingestion_checkpoints` automatically on its first poll.

Open http://localhost:8000/docs to try:

- `GET /usgs/latest`: live USGS preview; works without a database and lists missing parameters.
- `GET /api/observations/latest`: frontend data endpoint, reading exclusively from Tiger Data.
- `GET /ingestion/status`: configuration, active poll, last success/error type, processed row count and catch-up progress.
- `POST /ingestion/poll`: run one collection cycle immediately (also works when automatic polling is disabled).

The background worker starts automatically when `TIGER_DATABASE_URL` is set.
It polls every five minutes; no open browser or long-running HTTP request is needed.
Set `USGS_INGESTION_ENABLED=false` and restart to disable automatic collection.
Stopping the API stops collection. For continuous deployment, run this process on
an always-on host with automatic restart; serverless functions that sleep between
requests are unsuitable. Use one worker for consistent in-memory status. These
local development endpoints have no authentication; add access control before
exposing the manual poll endpoint publicly.

## Data behavior

The frontend's default **Current conditions** view fetches
`/api/observations/latest` every 15 seconds, and immediately when the tab becomes
visible or the browser reconnects. No refresh button is needed. Failed requests
retry automatically, and requests never overlap. The API selects the latest stored row
per requested parameter, ordered by observation time, and returns timestamps,
units, qualifiers and approval status. Missing parameters and NULL readings stay
missing. Readings older than 30 minutes are marked delayed. If refresh fails, the
page labels previously fetched values and retains their original timestamps.
There is no fallback to USGS or demo fixtures on this route. `/usgs/latest` remains
a separate diagnostic preview that is not used by the frontend.

Run the API on port 8000 and `bun run dev` in `client`. Vite proxies `/api` to
`http://localhost:8000`; restart Vite after changing its configuration. In production,
configure your web host/reverse proxy to forward `/api/*` to FastAPI, preserving
the path. Database credentials stay in the backend's `.env`; never put them in a
`VITE_` variable. The historical demo views remain available under Replay.

Requested codes: `32319,32316,00300,00400,00010,00671,00631,00608,00060,63680,00095`.
The station is configurable using `USGS_STATION_ID`.

The first cycle imports the previous 24 hours. Later cycles resume a database
checkpoint and reread six hours (configurable with `USGS_OVERLAP_HOURS`, 1-24)
to pick up delayed data and revisions. Outages catch up one day per cycle. Older
revisions or data delayed beyond the overlap require a separate historical backfill.
Pagination is followed; an incomplete request or failed database write rolls back
the cycle and its checkpoint. Failures retry at the next polling interval.

Each observation stores its original timestamp, time-series ID, parameter code,
units, approval status and raw USGS properties. The primary key is time-series ID
plus observation time; repeated polls upsert revised values without duplicating
observations. A database advisory lock prevents overlapping collectors. Missing or
nonnumeric values remain SQL NULL, never zero. Parameters absent from USGS are
reported as missing rather than synthesized.

The live station check on 2026-10-17 returned eight requested parameters;
`00671`, `00631` and `00608` were absent from latest continuous readings.
These nutrient parameters may require discrete water-quality samples from a
separate source. This collector does not substitute other stations or parameters.

USGS observations are instantaneous readings, whereas the logistic regression
currently expects daily min/mean/max attributes. Aggregate into those daily
features before feeding the model; do not pass raw readings directly.

Query recent stored data in Tiger Data:

```sql
SELECT observed_at, parameter_code, value, unit, approval_status
FROM usgs_observations
WHERE station_id = 'USGS-040851385'
ORDER BY observed_at DESC
LIMIT 100;
```

## Tests and references

```powershell
uv run python -m unittest discover -s tests -v
```

- [USGS continuous API and pagination](https://api.waterdata.usgs.gov/docs/ogcapi/)
- [USGS API keys for higher rate limits](https://api.waterdata.usgs.gov/docs/ogcapi/keys/)
- [Tiger Data hypertables](https://www.tigerdata.com/docs/reference/timescaledb/hypertables/create_hypertable)
