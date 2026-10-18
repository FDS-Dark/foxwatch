BEGIN;

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS usgs_observations (
    observed_at TIMESTAMPTZ NOT NULL,
    time_series_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    parameter_code TEXT NOT NULL,
    value DOUBLE PRECISION,
    unit TEXT,
    approval_status TEXT,
    source JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (time_series_id, observed_at)
);

SELECT create_hypertable('usgs_observations', by_range('observed_at'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS usgs_station_parameter_time
    ON usgs_observations (station_id, parameter_code, observed_at DESC);

CREATE TABLE IF NOT EXISTS usgs_ingestion_checkpoints (
    station_id TEXT PRIMARY KEY,
    through_time TIMESTAMPTZ NOT NULL
);

COMMIT;
