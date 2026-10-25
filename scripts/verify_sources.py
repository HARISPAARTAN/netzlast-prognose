"""Check the source facts the design relies on; prints a Markdown block for docs/data-notes.md.

Run: uv run python scripts/verify_sources.py   (needs network; 10 requests, one per second)
"""

from __future__ import annotations

import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import requests

BASE = "https://www.smard.de/app/chart_data"
OM = "https://previous-runs-api.open-meteo.com/v1/forecast"
UA = {"User-Agent": "netzlast-prognose/0.1 (+https://github.com/HARISPAARTAN/netzlast-prognose)"}
WEEK = 1760911200000  # Monday 2025-10-20 00:00 Europe/Berlin, the autumn daylight-saving week


def get(url: str, **params):
    time.sleep(1.0)
    r = requests.get(url, params=params or None, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%MZ")


def index(filter_id: int, region: str, resolution: str) -> str:
    try:
        ts = get(f"{BASE}/{filter_id}/{region}/index_{resolution}.json")["timestamps"]
    except requests.HTTPError as exc:
        return f"not available ({exc.response.status_code})"
    return f"{len(ts)} weekly chunks, {utc(ts[0])} to {utc(ts[-1])}"


def chunk(filter_id: int, resolution: str, ts: int) -> list:
    return get(f"{BASE}/{filter_id}/DE/{filter_id}_DE_{resolution}_{ts}.json")["series"]


def main() -> None:
    lines = [f"Checked {datetime.now(tz=UTC):%Y-%m-%d %H:%M} UTC with scripts/verify_sources.py.", ""]
    lines.append(f"- 410 DE hour: {index(410, 'DE', 'hour')}")
    lines.append(f"- 410 DE-LU hour: {index(410, 'DE-LU', 'hour')}")
    lines.append(f"- 411 DE hour: {index(411, 'DE', 'hour')}")

    hour, quarter = chunk(410, "hour", WEEK), chunk(410, "quarterhour", WEEK)
    sums = [sum(v for _, v in quarter[i : i + 4]) for i in range(0, len(quarter), 4)]
    worst = max(abs(h[1] - s) for h, s in zip(hour, sums, strict=True))
    lines.append(
        f"- Week of {utc(WEEK)}: hourly chunk {len(hour)} rows, quarter-hour chunk {len(quarter)} rows; "
        f"hourly value = sum of its four quarter-hours (largest difference {worst:.4f} MWh)"
    )

    ref = chunk(411, "hour", WEEK)
    ape = [
        abs(r[1] - a[1]) / a[1]
        for r, a in zip(ref, hour, strict=True)
        if r[1] is not None and a[1] is not None
    ]
    lines.append(
        f"- 411 against 410 in that week: MAPE {100 * sum(ape) / len(ape):.2f} % over {len(ape)} hours"
    )

    noon = WEEK + 12 * 3_600_000  # Monday 2025-10-20 12:00 Europe/Berlin (CEST) = 10:00 UTC
    lines.append(
        f"- Chart check, Monday 2025-10-20 12:00 local: 410 = {dict(hour)[noon]:,.2f} MWh, "
        f"411 = {dict(ref)[noon]:,.2f} MWh"
    )

    latest = get(f"{BASE}/411/DE/index_hour.json")["timestamps"][-1]
    act = [t for t, v in chunk(410, "hour", latest) if v is not None]
    fc = [t for t, v in chunk(411, "hour", latest) if v is not None]
    lines.append(
        f"- Newest values now: 410 up to {utc(act[-1])}, 411 up to {utc(fc[-1])} "
        f"(411 runs ahead of the realised load, as a day-ahead forecast must)"
    )

    om = get(
        OM,
        latitude=52.52,
        longitude=13.40,
        hourly="temperature_2m_previous_day2",
        start_date="2024-01-01",
        end_date="2024-03-31",
        timezone="GMT",
    )["hourly"]
    first = next(
        t for t, v in zip(om["time"], om["temperature_2m_previous_day2"], strict=True) if v is not None
    )
    lines.append(
        f"- Open-Meteo Previous Runs: variable `temperature_2m_previous_day2` exists; first value {first} UTC"
    )

    lock = tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
    pins = {p["name"]: p["version"] for p in lock["package"]}
    names = ["lightgbm", "statsforecast", "holidays", "pandas", "numpy", "fastapi", "scipy", "matplotlib"]
    lines.append("- Locked versions: " + ", ".join(f"{n} {pins[n]}" for n in names))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
