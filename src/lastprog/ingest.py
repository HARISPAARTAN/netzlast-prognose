"""Downloads: SMARD 410/411 into data/raw/smard and the observation store; Open-Meteo Previous Runs
(backtest only) into data/raw/openmeteo and the weather store."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import Settings
from .net import HttpClient
from .openmeteo import OpenMeteoClient
from .seed import read_seed_csv
from .smard import SmardClient
from .store import OBS_COLUMNS, OBS_KEY, WX_COLUMNS, WX_KEY, upsert
from .timekeys import local_midnight_utc


def fetch_smard(settings: Settings, start: date, end: date | None, raw_dir: Path | None = None) -> int:
    """Download 410 and 411 (region, hour) for [start, end] into the raw cache and upsert the store.

    With `raw_dir` only the chunk files are written there (used to create the committed fixtures).
    Returns the number of HTTP calls."""
    http = HttpClient(settings.data.user_agent, settings.data.min_request_interval_s)
    client = SmardClient(http, settings.data.smard_base_url, raw_dir or settings.paths.raw / "smard")
    lo = local_midnight_utc(start)
    hi = (
        local_midnight_utc(end + timedelta(days=1)) - pd.Timedelta(hours=1)
        if end
        else pd.Timestamp.now(tz="UTC")
    )
    d = settings.data
    for series, filter_id in (("load_actual", d.load_filter), ("load_tso_forecast", d.reference_filter)):
        rows = client.fetch_series(series, filter_id, d.region, d.resolution, lo, hi)
        if raw_dir is None and len(rows):
            upsert(settings.paths.store / "observations.parquet", rows, OBS_COLUMNS, OBS_KEY)
    return http.calls


def fetch_weather(settings: Settings, start: date, end: date) -> int:
    """Open-Meteo Previous Runs for the seed cities, two-day offset, into the weather store. Returns calls."""
    http = HttpClient(settings.data.user_agent, settings.data.min_request_interval_s)
    client = OpenMeteoClient(http, settings.weather.base_url, settings.paths.raw / "openmeteo")
    frames = []
    for city in read_seed_csv(settings.paths.seed / "staedte.csv"):
        frames.append(
            client.fetch_city(
                city["name"],
                float(city["lat"]),
                float(city["lon"]),
                list(settings.weather.variables),
                settings.weather.offset_days,
                start,
                end,
            )
        )
    upsert(settings.paths.store / "weather.parquet", pd.concat(frames, ignore_index=True), WX_COLUMNS, WX_KEY)
    return http.calls
