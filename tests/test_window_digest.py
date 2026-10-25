"""scripts/window_digest.py: the digest depends on the window rows only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "window_digest", Path(__file__).resolve().parents[1] / "scripts" / "window_digest.py"
)
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)

END = "2026-10-01T22:00:00Z"


def _frames():
    ts = pd.date_range("2026-09-30 20:00", periods=6, freq="h", tz="UTC")  # last two are at/after END
    obs = pd.concat(
        [
            pd.DataFrame({"series": s, "region": "DE", "ts_utc": ts, "value": np.arange(6.0) + k})
            for k, s in enumerate(["load_actual", "load_tso_forecast"])
        ],
        ignore_index=True,
    )
    obs["fetched_at_utc"] = pd.Timestamp("2026-10-25T10:00:00Z")
    wx = pd.DataFrame(
        {
            "city": "Berlin",
            "variable": "temperature_2m",
            "offset_days": 2,
            "model": "m",
            "ts_utc": ts,
            "value": 1.5,
        }
    )
    wx["fetched_at_utc"] = pd.Timestamp("2026-10-25T10:00:00Z")
    return obs, wx


def test_digest_ignores_fetch_stamp_order_and_rows_after_the_window():
    obs, wx = _frames()
    end = "2026-09-30T23:00:00Z"  # keep the first three hours
    base = wd.window_digest(obs, wx, end)
    assert base["observations"]["rows"] == 6
    shuffled = obs.sample(frac=1.0, random_state=1).assign(
        fetched_at_utc=pd.Timestamp("2027-01-01", tz="UTC")
    )
    assert wd.window_digest(shuffled, wx, end)["combined_sha256"] == base["combined_sha256"]
    later = obs.copy()
    later.loc[later["ts_utc"] >= pd.Timestamp(end), "value"] = -1.0  # revision after the window
    assert wd.window_digest(later, wx, end)["combined_sha256"] == base["combined_sha256"]


def test_digest_changes_with_a_value_inside_the_window_and_with_nan():
    obs, wx = _frames()
    end = "2026-09-30T23:00:00Z"
    base = wd.window_digest(obs, wx, end)["combined_sha256"]
    changed = obs.copy()
    changed.loc[0, "value"] += 1e-9
    assert wd.window_digest(changed, wx, end)["combined_sha256"] != base
    nan = obs.copy()
    nan.loc[0, "value"] = np.nan
    assert wd.window_digest(nan, wx, end)["combined_sha256"] != base
    wx2 = wx.copy()
    wx2.loc[0, "value"] = 2.5
    assert wd.window_digest(obs, wx2, end)["combined_sha256"] != base


def test_other_series_are_outside_the_window_definition():
    obs, wx = _frames()
    extra = obs.iloc[:1].assign(series="price_da", value=99.0)
    both = pd.concat([obs, extra], ignore_index=True)
    assert (
        wd.window_digest(both, wx, END)["combined_sha256"]
        == wd.window_digest(obs, wx, END)["combined_sha256"]
    )
