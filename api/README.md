# FoxWatch API

One FastAPI application serves USGS observations and evidence-backed bloom
favorability insights. It collects continuous measurements for Fox River at Green
Bay, station `USGS-040851385`, into a Tiger Data (TimescaleDB/PostgreSQL)
hypertable. Layering matches the full-stack-app template:
**routers → services → databridge → engine**.

## Layout

```text
api/
  main.py                 # FastAPI app + USGS collector lifecycle
  settings.py             # APP__* settings, paths, Gemini, legacy Tiger/USGS env
  dependencies.py         # Engine/databridge/service singletons (+ optional JWT)
  routers/                # HTTP only — status codes, deps, no business logic
  services/               # All domain logic
    usgs_ingestion.py     # Background USGS → Postgres collector (write path)
    usgs_client.py        # USGS OGC API fetch/normalize
    observations.py       # Latest readings via databridge (read path)
    predictions.py        # Logistic regression inference
    bfi.py                # BFI insights orchestration
    bfi_scoring.py        # Rule-based bloom favorability index
    bfi_insights.py       # RAG + Gemini narrative synthesis
    bfi_retrieval.py      # Hybrid evidence retrieval
    gemini_client.py      # Optional Gemini API client
    rag_*.py              # Corpus chunk/embed/ingest pipeline
    ml/                   # Offline train/eval scripts + model artifacts
  models/                 # Pydantic API models + domain constants (usgs, bfi_factors)
  databridge/             # SQL → DataFrame
  engine/                 # SQLAlchemy async Postgres pool
database/                 # Local TimescaleDB + db-upgrader migrations
```

Build the RAG index from `api/`:

```powershell
uv sync --group rag
uv run python -m services.rag_ingest
```

## Run

From the repository root:

```powershell
cd api
uv sync
# Create api/.env with TIGER_DATABASE_URL set to your Tiger Cloud connection URL.
uv run python main.py
```

For reload mode, run `uv run uvicorn main:app --reload` from `api/`.
From the repository root, use `uvicorn api.main:app --reload` with the API
environment activated. The old `foxwatch.main:app` entry point has been removed.
Only one API process is needed on port 8000.

Put `GEMINI_API_KEY` and optional `GEMINI_MODEL` in the repo-root `.env` (see
`../.env.example`). Put the Tiger/Timescale URL in `api/.env` as
`TIGER_DATABASE_URL`, `TIMESCALE_SERVICE_URL`, or `INGEST_DATABASE_URL`.
Environment variables already set in the shell take precedence, then `api/.env`,
then repo-root `.env`. `uv sync` installs the core API. Optional RAG/Gemini
packages install with `uv sync --group rag`. Without them, the BFI endpoint
uses hash embeddings and local synthesis fallbacks; it still requires a built
RAG index under `data/rag/index/`.

Copy the PostgreSQL connection URL from your Tiger Cloud service's connection
details, including its port, database, password and `sslmode=require`. Keep it in
the ignored `.env` file. The database must have TimescaleDB enabled and the user
must have permission to create tables and hypertables. The collector creates
`usgs_observations` and `usgs_ingestion_checkpoints` automatically on its first poll.

Open http://localhost:8000/docs to try:

- `GET /`: service links.
- `GET /api/health`: RAG index presence and Gemini configuration.
- `POST /api/v1/bfi/insights`: bloom favorability scores and supporting evidence.
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

Run the API on port 8000 and `bun run dev` in `client`. The UI opens at
`http://127.0.0.1:6173`. Vite runs with Bun explicitly; this avoids using an older
system Node installation. Port 6173 avoids the Windows-reserved 5173 range. Vite proxies `/api` to
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

USGS observations are instantaneous readings, whereas the model training CSVs
contain daily summaries. The v2 prediction endpoint explicitly supports latest
instantaneous inputs, with this difference documented in its response. Its
validation results on daily means do not measure instantaneous prediction quality.

Query recent stored data in Tiger Data:

```sql
SELECT observed_at, parameter_code, value, unit, approval_status
FROM usgs_observations
WHERE station_id = 'USGS-040851385'
ORDER BY observed_at DESC
LIMIT 100;
```

## Tests and references

### Mean-only logistic regression v2

Train and save the model from `data/labeled_openai.csv` (run from `api`):

```powershell
uv run python -m services.ml.logistic_regression_v2
```

This writes `model/artifacts/logistic_regression_v2.pkl` and an accompanying JSON
validation report. These generated files are ignored by Git; train on deployment
or copy your trusted generated artifact there. The API caches the fitted model
and reloads it when the artifact changes. Training is never performed per request.

Only seven `_mean` columns are used: chlorophyll fluorescence, discharge,
dissolved oxygen, phycocyanin fluorescence, specific conductance, turbidity and
water temperature. pH is excluded because this CSV has `ph_median`, not `ph_mean`.
Training uses standard scaling and class-balanced logistic regression. Validation
is stratified five-fold cross-validation with preprocessing fitted within each fold;
the saved model is then fitted on all rows. The CSV currently has 358 negative and
8 positive labels. All positives are near the end, so a chronological 80/20 split
would leave training without any positive class. Random stratified validation does
not establish future forecasting performance.

`GET /api/predictions/latest` reads the same station and parameter measurements
from Tiger Data as the frontend. If the latest row is NULL, a single database
query retrieves that parameter's most recent non-NULL value at or before the latest
observation time, within the same station. It searches all stored history, including
across restarts; zero is a valid value. No external USGS calls or training-data
imputation are used for live inference. If a feature has never been measured,
the endpoint returns `status: "unavailable"` with `missing_features` and no prediction.

Available responses include `algal_bloom` (0/1), `probability`, the 0.5 threshold,
model version, and `inputs`. Each input records its feature, parameter code, value,
unit, observation time, quality metadata and `used_fallback`. An older non-NULL
reading may be used indefinitely, so consumers should inspect timestamps. This
does not change the raw values displayed in Current conditions.

The Current conditions page requests a prediction alongside its readings every
15 seconds. Its prediction card displays `probability` as a decimal and buckets
the unrounded score as low (`<0.5`), medium (`>=0.5` and `<0.8`), or high (`>=0.8`).
The card shows missing-input and request-error states instead of a stale score,
and identifies predictions using carried-forward or delayed measurements.

Live inputs intentionally use instantaneous values, as requested, whereas training
uses daily means. This difference is included in the prediction response's
`limitations`; daily-mean validation does not validate instantaneous predictions.
Class-weighted probability scores are not calibrated bloom risks.

```powershell
uv run python -m unittest discover -s tests -v
```

- [USGS continuous API and pagination](https://api.waterdata.usgs.gov/docs/ogcapi/)
- [USGS API keys for higher rate limits](https://api.waterdata.usgs.gov/docs/ogcapi/keys/)
- [Tiger Data hypertables](https://www.tigerdata.com/docs/reference/timescaledb/hypertables/create_hypertable)


## X-Ray the Bay

Open `http://127.0.0.1:6173/#/replay` for the historical FLAMe experiment.
The default Bay gradient view renders location-only and satellite-informed
full-survey RF predictions over expanded satellite coverage. It includes
extrapolation, marked with diagonal stripes beyond 3 km of training evidence.
The actual satellite mosaic is available in the layer selector.
The X-Ray experiment compares location-only and satellite-informed held-out predictions as
linked gradient maps, then reveals the measured boat transect. The same
0–16 RFU color scale applies to every holdout panel; the bay overview uses
0–4 RFU for lower-level variation, with larger values saturated at yellow. Individual samples are optional.
Segment 32 demonstrates plume recovery; segments 31 and 17 provide contrasting
cases. `#/investigate` explains the stored evidence with source links.

The read-only `/api/xray` routes serve the portable `data/xray` export without
querying the database or fitting models. `/survey` returns timestamped measured
bins; `/segments/{id}?stage=hidden|location|satellite|reveal` controls the values
shown in the experiment. `/holdouts/{id}/{model}` serves prediction fields;
`/evidence/{source_id}` serves the underlying research records. Restart the API
after updating exports because JSON metadata is cached in process.

To regenerate exports, run `scripts/export_xray_demo.py` followed by
`scripts/export_xray_holdout_maps.py` from the repository root using the research
Python environment. These require the existing Phase 1/2 artifacts and research
dependencies. The map exporter reproduces the saved fold predictions before
rendering, excluding hidden targets and their buffers. Display interpolation
smooths the 100 m prediction grid; it does not add observations or change scores.
Local exports retain the valid-water mask and 3 km training-support limit.
After generating the expanded overview, run
`scripts/export_xray_holdout_maps.py --bay` to render those same held-out fits
over the wider satellite mosaic. This export marks extrapolation beyond 3 km
instead of clipping it. The experiment defaults to Whole bay, with a Hidden
segment zoom option. Scored track predictions retain each bin's original scene;
the multi-date field is separate visualization, not additional validation. The full-survey fit in the survey overlay is
separate from holdout validation. RFU is fluorescence, not harmful-bloom risk.

The expanded overview is generated separately with
`scripts/fetch_xray_bay_scenes.py` and `scripts/export_xray_bay_map.py` in the
research Python environment. The downloader selects adjacent July 1, 2025
Sentinel-2 tiles (16TDQ/16TDR) and a June 30 tile (16TER) for northeastern
coverage, plus July 3 tiles (16TDR/16TER) to fill remaining cloud or quality
gaps. It caches original scaled 20 m reflectance/QA and true-color windows
under `research/xray_bay/phase2_satellite/bay_overview`, leaving holdout inputs
unchanged. The overview uses the same 100 m valid-water sampling and model
features, evaluated on a 200 m display grid. July 1 valid pixels take priority;
June 30 fills missing coverage, followed by July 3 where needed. This is a multi-date mosaic, not a simultaneous
bay-wide measurement. Cloud, land, and failed-quality pixels remain masked.
Portable images and acquisition metadata are in `data/xray/bay`; original
research caches are not required by the running API. Per-cell scene provenance,
training distance, features and predictions are retained in `overview_inputs.npz`.
