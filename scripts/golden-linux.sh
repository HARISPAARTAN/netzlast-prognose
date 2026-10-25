#!/usr/bin/env bash
# Regenerate data/fixtures/golden_metrics.json on ubuntu:24.04, the CI operating system.
# Run from the repository root (PowerShell):
#   docker run --rm -v "${PWD}:/src" -w /src ubuntu:24.04 bash scripts/golden-linux.sh
set -euo pipefail
apt-get update -qq
apt-get install -y -qq curl ca-certificates git libgomp1 > /dev/null
curl -LsSf https://astral.sh/uv/0.11.8/install.sh | sh > /dev/null
export PATH="$HOME/.local/bin:$PATH" UV_PROJECT_ENVIRONMENT=/tmp/venv LASTPROG_OFFLINE=1 NUMBA_CPU_NAME=generic
git config --global --add safe.directory /src
uv sync --locked --all-extras --dev --python 3.13
uv run --no-sync lastprog backtest --period fixtures --run-id golden-linux --write-golden
uv run --no-sync pytest tests/test_backtest_golden.py -q
