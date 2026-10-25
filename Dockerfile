# Netzlast-Prognose service image: core dependencies only (no statsforecast or matplotlib).
# Base images are pinned by digest (python:3.13-slim-bookworm, uv 0.11.8). The uv binary stays in the build stage.
FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS build
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.8@sha256:3b7b60a81d3c57ef471703e5c83fd4aaa33abcd403596fb22ab07db85ae91347 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1 UV_PROJECT_ENVIRONMENT=/app/.venv \
    LASTPROG_CONFIG=/app/config.toml PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY config.toml ./
COPY src ./src
COPY data/seed ./data/seed
COPY data/fixtures/smard ./data/fixtures/smard
RUN uv sync --locked --no-dev && LASTPROG_OFFLINE=1 lastprog train --period fixtures --as-of 2025-10-25

FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
WORKDIR /app
ENV LASTPROG_CONFIG=/app/config.toml LASTPROG_MODE=demo PATH="/app/.venv/bin:$PATH"
COPY --from=build /app /app
USER app
EXPOSE 8000
# /health answers 503 when the status is "degraded" (no model, or stale data in full mode), which urlopen raises on.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "lastprog.api:app", "--host", "0.0.0.0", "--port", "8000"]
