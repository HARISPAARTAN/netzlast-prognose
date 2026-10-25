# Netzlast-Prognose service image: core dependencies only (no statsforecast or matplotlib).
FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1 UV_PROJECT_ENVIRONMENT=/app/.venv \
    LASTPROG_CONFIG=/app/config.toml LASTPROG_MODE=demo PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY config.toml ./
COPY src ./src
COPY data/seed ./data/seed
COPY data/fixtures/smard ./data/fixtures/smard
RUN uv sync --locked --no-dev && LASTPROG_OFFLINE=1 lastprog train --period fixtures --as-of 2025-10-25
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "lastprog.api:app", "--host", "0.0.0.0", "--port", "8000"]
