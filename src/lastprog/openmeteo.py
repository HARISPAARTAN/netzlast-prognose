"""Open-Meteo Previous Runs client (weather data by Open-Meteo.com, CC BY 4.0), backtest only.

`{variable}_previous_day2` is "the value that was predicted 48 hours before valid time" (Open-Meteo docs).
Requests: {base}?latitude=..&longitude=..&hourly=temperature_2m_previous_day2,shortwave_radiation_previous_day2
&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&timezone=GMT -> {"hourly": {"time": [...], "<var>": [...]}}.
One request per city; responses are cached under data/raw/openmeteo/.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from .net import HttpClient

MODEL = "best_match"


def hourly_name(variable: str, offset_days: int) -> str:
    return f"{variable}_previous_day{offset_days}"


def parse_response(payload: dict, city: str, variables: list[str], offset_days: int) -> pd.DataFrame:
    """Long rows (city, ts_utc, variable, offset_days, model, value); nulls stay NaN."""
    hourly = payload["hourly"]
    ts = pd.to_datetime(hourly["time"]).tz_localize("UTC")
    parts = []
    for var in variables:
        values = pd.to_numeric(pd.Series(hourly[hourly_name(var, offset_days)], dtype="object")).astype(
            "float64"
        )
        parts.append(
            pd.DataFrame(
                {
                    "city": city,
                    "ts_utc": ts,
                    "variable": var,
                    "offset_days": offset_days,
                    "model": MODEL,
                    "value": values.to_numpy(),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


class OpenMeteoClient:
    def __init__(self, http: HttpClient, base_url: str, cache_dir: Path) -> None:
        self.http = http
        self.base_url = base_url
        self.cache_dir = Path(cache_dir)

    def fetch_city(
        self,
        city: str,
        lat: float,
        lon: float,
        variables: list[str],
        offset_days: int,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        path = self.cache_dir / f"{city}_{start}_{end}_d{offset_days}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(hourly_name(v, offset_days) for v in variables),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "timezone": "GMT",
            }
            payload = self.http.get_json(self.base_url, params=params)
            if "hourly" not in payload:
                raise ValueError(f"{city}: Open-Meteo response without 'hourly': {str(payload)[:200]}")
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_name(path.name + ".part")
            part.write_text(json.dumps(payload), encoding="utf-8")
            part.replace(path)
        return parse_response(payload, city, variables, offset_days)
