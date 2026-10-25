"""Window-restricted digest of the data store (and the matching Parquet extract).

The whole-store hash in run.json (`Store.snapshot()`) covers every row, including rows fetched after the
protocol runs, so it changes whenever the live job or a refit refreshes the store. This script hashes only
the rows inside the protocol window: load (filter 410, `load_actual`), the TSO forecast (filter 411,
`load_tso_forecast`) and the weather rows with `ts_utc` strictly before the end of the last scored hour.

Canonical serialisation (independent of pandas or pyarrow versions):
  observations  one line per row, sorted by (series, region, ts_utc):
                "<series>|<region>|<ts_utc as YYYY-MM-DDTHH:MM:SSZ>|<value>"
  weather       one line per row, sorted by (city, variable, offset_days, model, ts_utc):
                "<city>|<variable>|<offset_days>|<model>|<ts_utc as YYYY-MM-DDTHH:MM:SSZ>|<value>"
  <value> is Python repr(float) (shortest round-trip form) or "nan"; fetched_at_utc, chunk_ts_ms and
  filter_id are not part of the digest. Every line ends with "\\n"; the part digest is the SHA-256 of the
  UTF-8 bytes of the lines. The combined digest is the SHA-256 of
  "observations:<digest>\\nweather:<digest>\\n".

Usage (only pandas and pyarrow are needed):
  uv run python scripts/window_digest.py --store data/store
  uv run python scripts/window_digest.py --store data/store --extract-dir out/   # also write the extract
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

# Last scored target hour: origin 2026-09-30 forecasts the local day 2026-10-01 (CEST, UTC+2), which ends
# at 2026-10-01 22:00 UTC. The window is [start of the store, END) in UTC.
END_UTC_EXCLUSIVE = "2026-10-01T22:00:00Z"
OBS_SERIES = ("load_actual", "load_tso_forecast")
OBS_SORT = ["series", "region", "ts_utc"]
WX_SORT = ["city", "variable", "offset_days", "model", "ts_utc"]


def _fmt_value(v: float) -> str:
    return "nan" if v != v else repr(float(v))


def _ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def restrict(obs: pd.DataFrame, wx: pd.DataFrame, end_utc_exclusive: str = END_UTC_EXCLUSIVE):
    """The rows of the protocol window, in the store's own column layout."""
    end = pd.Timestamp(end_utc_exclusive)
    o = obs[obs["series"].isin(OBS_SERIES) & (pd.to_datetime(obs["ts_utc"], utc=True) < end)]
    w = wx[pd.to_datetime(wx["ts_utc"], utc=True) < end]
    return o.reset_index(drop=True), w.reset_index(drop=True)


def _digest(lines: list[str]) -> str:
    h = hashlib.sha256()
    for line in lines:
        h.update(line.encode("utf-8"))
    return h.hexdigest()


def observation_digest(obs: pd.DataFrame) -> tuple[str, int]:
    d = obs.assign(_t=pd.to_datetime(obs["ts_utc"], utc=True)).sort_values(
        ["series", "region", "_t"], kind="mergesort"
    )
    ts = _ts(d["_t"])
    lines = [
        f"{s}|{r}|{t}|{_fmt_value(v)}\n"
        for s, r, t, v in zip(d["series"], d["region"], ts, d["value"], strict=True)
    ]
    return _digest(lines), len(lines)


def weather_digest(wx: pd.DataFrame) -> tuple[str, int]:
    d = wx.assign(_t=pd.to_datetime(wx["ts_utc"], utc=True)).sort_values(
        ["city", "variable", "offset_days", "model", "_t"], kind="mergesort"
    )
    ts = _ts(d["_t"])
    lines = [
        f"{c}|{v}|{int(o)}|{m}|{t}|{_fmt_value(x)}\n"
        for c, v, o, m, t, x in zip(
            d["city"], d["variable"], d["offset_days"], d["model"], ts, d["value"], strict=True
        )
    ]
    return _digest(lines), len(lines)


def window_digest(obs: pd.DataFrame, wx: pd.DataFrame, end_utc_exclusive: str = END_UTC_EXCLUSIVE) -> dict:
    o, w = restrict(obs, wx, end_utc_exclusive)
    d_o, n_o = observation_digest(o)
    d_w, n_w = weather_digest(w)
    combined = hashlib.sha256(f"observations:{d_o}\nweather:{d_w}\n".encode()).hexdigest()
    return {
        "window_end_utc_exclusive": end_utc_exclusive,
        "observations": {
            "series": list(OBS_SERIES),
            "rows": n_o,
            "first_ts_utc": str(o["ts_utc"].min()),
            "last_ts_utc": str(o["ts_utc"].max()),
            "sha256": d_o,
        },
        "weather": {
            "rows": n_w,
            "first_ts_utc": str(w["ts_utc"].min()),
            "last_ts_utc": str(w["ts_utc"].max()),
            "sha256": d_w,
        },
        "combined_sha256": combined,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", required=True, help="directory with observations.parquet and weather.parquet")
    p.add_argument("--end-utc-exclusive", default=END_UTC_EXCLUSIVE)
    p.add_argument(
        "--extract-dir", help="write the window rows here as observations.parquet / weather.parquet"
    )
    p.add_argument("--out", help="also write the digest JSON to this file")
    a = p.parse_args(argv)

    store = Path(a.store)
    obs = pd.read_parquet(store / "observations.parquet")
    wx = pd.read_parquet(store / "weather.parquet")
    result = window_digest(obs, wx, a.end_utc_exclusive)
    text = json.dumps(result, indent=1) + "\n"
    sys.stdout.write(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    if a.extract_dir:
        o, w = restrict(obs, wx, a.end_utc_exclusive)
        out = Path(a.extract_dir)
        out.mkdir(parents=True, exist_ok=True)
        o.sort_values(OBS_SORT, kind="mergesort").to_parquet(out / "observations.parquet", index=False)
        w.sort_values(WX_SORT, kind="mergesort").to_parquet(out / "weather.parquet", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
