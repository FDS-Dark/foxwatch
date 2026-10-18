# Build context: repository root (docker build -f api/Dockerfile .)
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS base

WORKDIR /app

COPY api/pyproject.toml api/uv.lock api/README.md ./api/
RUN cd api && uv sync --frozen --no-dev --group rag

COPY api ./api
COPY data/labeled_openai.csv data/labeled_openai.csv
COPY data/rag/index/chunks.jsonl data/rag/index/chunks.jsonl
COPY data/rag/index/index_meta.json data/rag/index/index_meta.json

WORKDIR /app/api

RUN uv run python -m services.ml.logistic_regression_v2

ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn main:app --host ${HOST} --port ${PORT}"]
