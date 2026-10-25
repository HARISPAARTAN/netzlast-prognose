"""Command line: uv run lastprog <command>."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import typer

from .config import load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Netzlast-Prognose")


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LASTPROG_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _settings(period: str | None = None):
    s = load_settings()
    return s.for_fixtures() if period == "fixtures" else s


@app.callback()
def main() -> None:
    """Netzlast-Prognose: probabilistic day-ahead forecasts of German grid load."""


@app.command()
def fetch(
    from_: str = typer.Option(None, "--from", help="First local day (default: history_start)"),
    to: str = typer.Option(None, "--to", help="Last local day (default: now)"),
    weather: bool = typer.Option(
        False, "--weather", help="Also fetch Open-Meteo Previous Runs (backtest only)"
    ),
    raw_dir: Path = typer.Option(
        None, "--raw-dir", help="Only fill this chunk directory (fixtures), no store"
    ),
) -> None:
    """Download SMARD 410/411 (DE, hour) into data/raw and data/store."""
    from .ingest import fetch_smard, fetch_weather

    _setup_logging()
    s = _settings()
    start = date.fromisoformat(from_) if from_ else s.data.history_start
    end = date.fromisoformat(to) if to else None
    calls = fetch_smard(s, start, end, raw_dir)
    typer.echo(f"smard: {calls} HTTP calls")
    if weather:
        wx_end = end or s.backtest.test[1]
        calls = fetch_weather(s, s.weather.start, wx_end)
        typer.echo(f"open-meteo: {calls} HTTP calls")
