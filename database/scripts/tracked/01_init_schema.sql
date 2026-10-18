BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    user_id     TEXT PRIMARY KEY,
    email       TEXT UNIQUE,
    name        TEXT,
    picture_url TEXT,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON auth.users(email);

CREATE TABLE IF NOT EXISTS auth.permissions (
    perm_id   SMALLINT PRIMARY KEY CHECK (perm_id BETWEEN 0 AND 63),
    name      TEXT UNIQUE NOT NULL,
    comment   TEXT
);

CREATE TABLE IF NOT EXISTS auth.roles (
    role_id    SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    perm_mask  BIGINT NOT NULL DEFAULT 0,
    metadata   JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth.user_roles (
    user_id TEXT REFERENCES auth.users(user_id) ON DELETE CASCADE,
    role_id INT  REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

COMMIT;
