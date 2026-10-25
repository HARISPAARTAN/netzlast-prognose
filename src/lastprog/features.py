"""Features for one target day, computed in Europe/Berlin local time per target hour.

`build_features(store, target_day, cutoff, spec)` is pure: it reads only load observations with
ts_utc < cutoff and weather values of the configured lead offset (two days). The reference forecast
(filter 411) is never a feature. Lags are named relative to the issue day D = target_day - 1.

Weather timestamp convention (see docs/data-notes.md): the load row stamped t covers [t, t+1 h). Instantaneous
weather variables (temperature_2m) are the value AT the stamp, so the load hour t uses the weather stamped t.
shortwave_radiation is the MEAN OF THE PRECEDING HOUR, so the load hour [t, t+1 h) uses the radiation stamped
t+1 h (a shift of one hour, `RADIATION_SHIFT`). With the two-day `_previous_day2` offset the run behind the
value stamped t+1 h is 48 h older, which is at most the cut-off (local midnight of the issue day) plus one
hour on the 25-hour autumn day; no run issued after the cut-off enters a 24-hour or 23-hour day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

from .seed import read_seed_csv
from .store import Store
from .timekeys import BERLIN, day_index, hours_in_day, local_midnight_utc

CALENDAR_FEATURES = [
    "hour",
    "weekday",
    "hour_x_weekday",
    "doy_sin1",
    "doy_cos1",
    "doy_sin2",
    "doy_cos2",
    "doy_sin3",
    "doy_cos3",
    "dst_day",
    "days_to_xmas",
    "xmas_period",
    "hol_national",
    "hol_share",
    "hol_share_prev",
    "hol_share_next",
    "bridge_day",
]
LAG_FEATURES = ["lag_d1", "lag_d2", "lag_d6", "lag_d13", "d1_mean", "d1_max", "d7_mean", "ratio_d1_d8"]
WEATHER_FEATURES = ["wx_temp", "wx_hdh", "wx_cdh", "wx_ssr"]
HDH_BASE_C = 15.0
CDH_BASE_C = 22.0
LOOKBACK_DAYS = 16
RADIATION_SHIFT = pd.Timedelta(hours=1)  # shortwave_radiation is stamped at the END of its hour


@cache
def _national(year: int) -> frozenset[date]:
    return frozenset(holidays.country_holidays("DE", years=year).keys())


@cache
def _by_land(code: str, year: int) -> frozenset[date]:
    return frozenset(holidays.country_holidays("DE", subdiv=code, years=year).keys())


class HolidayCalendar:
    """National holidays, population-weighted share of Länder with a holiday, bridge days."""

    def __init__(self, population: dict[str, int]) -> None:
        if len(population) != 16:
            raise ValueError(f"expected 16 Länder, got {len(population)}")
        self.population = dict(population)
        self.total = sum(self.population.values())

    @classmethod
    def from_seed(cls, seed_dir: Path) -> HolidayCalendar:
        rows = read_seed_csv(Path(seed_dir) / "bundesland_bevoelkerung.csv")
        return cls({r["code"]: int(r["population"]) for r in rows})

    def is_national(self, d: date) -> bool:
        return d in _national(d.year)

    def share(self, d: date) -> float:
        """Population share (0..1) of Länder in which `d` is a public holiday; exactly 1.0 when all are."""
        covered = sum(pop for code, pop in self.population.items() if d in _by_land(code, d.year))
        return covered / self.total

    def is_bridge(self, d: date) -> bool:
        """Working day between a holiday (share >= 0.5) and a weekend: Friday after, or Monday before."""
        if d.weekday() >= 5 or self.share(d) >= 0.5:
            return False
        prev, nxt = d - timedelta(days=1), d + timedelta(days=1)
        return (self.share(prev) >= 0.5 and nxt.weekday() == 5) or (
            self.share(nxt) >= 0.5 and prev.weekday() == 6
        )


@dataclass(frozen=True)
class FeatureSpec:
    calendar: HolidayCalendar
    with_weather: bool = False
    weather_offset_days: int = 2
    city_weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.weather_offset_days < 2:
            raise ValueError("weather offset below two days leaks information for the late hours of D+1")
        if self.with_weather and not self.city_weights:
            raise ValueError("weather features need city weights")

    @property
    def columns(self) -> list[str]:
        return CALENDAR_FEATURES + LAG_FEATURES + (WEATHER_FEATURES if self.with_weather else [])


def city_weights_from_seed(seed_dir: Path) -> dict[str, float]:
    """Weight of each weather city = population of its Land, normalised to sum 1."""
    pop = {
        r["code"]: int(r["population"]) for r in read_seed_csv(Path(seed_dir) / "bundesland_bevoelkerung.csv")
    }
    cities = read_seed_csv(Path(seed_dir) / "staedte.csv")
    raw = {c["name"]: float(pop[c["land"]]) for c in cities}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def _calendar_block(target_day: date, idx: pd.DatetimeIndex, cal: HolidayCalendar) -> dict[str, np.ndarray]:
    local = idx.tz_convert(BERLIN)
    n = len(idx)
    hour = local.hour.to_numpy(dtype="float64")
    weekday = np.full(n, float(target_day.weekday()))
    doy = float(target_day.timetuple().tm_yday)
    out = {"hour": hour, "weekday": weekday, "hour_x_weekday": weekday * 24 + hour}
    for k in (1, 2, 3):
        out[f"doy_sin{k}"] = np.full(n, math.sin(2 * math.pi * k * doy / 365.25))
        out[f"doy_cos{k}"] = np.full(n, math.cos(2 * math.pi * k * doy / 365.25))
    xmas = date(target_day.year if target_day.month >= 7 else target_day.year - 1, 12, 25)
    out["dst_day"] = np.full(n, float(hours_in_day(target_day) != 24))
    out["days_to_xmas"] = np.full(n, float(max(-60, min(60, (target_day - xmas).days))))
    out["xmas_period"] = np.full(n, float(target_day.month == 12 and target_day.day >= 24))
    out["hol_national"] = np.full(n, float(cal.is_national(target_day)))
    out["hol_share"] = np.full(n, cal.share(target_day))
    out["hol_share_prev"] = np.full(n, cal.share(target_day - timedelta(days=1)))
    out["hol_share_next"] = np.full(n, cal.share(target_day + timedelta(days=1)))
    out["bridge_day"] = np.full(n, float(cal.is_bridge(target_day)))
    return out


def _wallclock(series: pd.Series) -> pd.Series:
    """Re-index a UTC series by naive local wall-clock time; the repeated autumn hour keeps its first value."""
    s = pd.Series(series.to_numpy(), index=series.index.tz_convert(BERLIN).tz_localize(None))
    return s[~s.index.duplicated(keep="first")]


def _lag_block(load: pd.Series, target_day: date, idx: pd.DatetimeIndex, cutoff: pd.Timestamp) -> dict:
    issue_day = target_day - timedelta(days=1)
    lo = local_midnight_utc(target_day - timedelta(days=LOOKBACK_DAYS))
    hist = load[(load.index >= lo) & (load.index < cutoff)]
    wall = _wallclock(hist)
    target_wall = idx.tz_convert(BERLIN).tz_localize(None)
    out: dict[str, np.ndarray] = {}
    for name, days_back in (("lag_d1", 2), ("lag_d2", 3), ("lag_d6", 7), ("lag_d13", 14)):
        keys = target_wall - pd.Timedelta(days=days_back)
        if wall.empty:
            out[name] = np.full(len(idx), np.nan)
        else:
            # Exact wall-clock match; the hour missing on the spring transition day takes the hour before.
            out[name] = wall.reindex(keys, method="ffill", tolerance=pd.Timedelta(hours=1)).to_numpy(
                "float64"
            )

    def day_values(d: date) -> np.ndarray:
        a, b = local_midnight_utc(d), local_midnight_utc(d + timedelta(days=1))
        return hist[(hist.index >= a) & (hist.index < b)].to_numpy("float64")

    def nanstat(fn, values: np.ndarray) -> float:
        values = values[~np.isnan(values)]
        return float(fn(values)) if values.size else np.nan

    d1 = day_values(issue_day - timedelta(days=1))
    d8 = day_values(issue_day - timedelta(days=8))
    week = np.concatenate([day_values(issue_day - timedelta(days=k)) for k in range(1, 8)])
    d1_mean, d8_mean = nanstat(np.mean, d1), nanstat(np.mean, d8)
    n = len(idx)
    out["d1_mean"] = np.full(n, d1_mean)
    out["d1_max"] = np.full(n, nanstat(np.max, d1))
    out["d7_mean"] = np.full(n, nanstat(np.mean, week))
    out["ratio_d1_d8"] = np.full(n, d1_mean / d8_mean if d8_mean and not np.isnan(d8_mean) else np.nan)
    return out


def _weather_block(store: Store, idx: pd.DatetimeIndex, spec: FeatureSpec) -> dict[str, np.ndarray]:
    wide = store.weather_wide(spec.weather_offset_days)

    def weighted(variable: str, shift: pd.Timedelta | None = None) -> np.ndarray:
        # The value for load hour t is the one stamped t + shift (see the module docstring).
        frame = wide.reindex(idx if shift is None else idx + shift)
        num = np.zeros(len(idx))
        den = np.zeros(len(idx))
        for city, w in spec.city_weights.items():
            col = f"{city}|{variable}"
            if col not in frame:
                continue
            v = frame[col].to_numpy("float64")
            ok = ~np.isnan(v)
            num[ok] += w * v[ok]
            den[ok] += w
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)

    temp = weighted("temperature_2m")
    return {
        "wx_temp": temp,
        "wx_hdh": np.maximum(0.0, HDH_BASE_C - temp),
        "wx_cdh": np.maximum(0.0, temp - CDH_BASE_C),
        "wx_ssr": weighted("shortwave_radiation", RADIATION_SHIFT),
    }


def build_features(store: Store, target_day: date, cutoff: pd.Timestamp, spec: FeatureSpec) -> pd.DataFrame:
    """Feature frame indexed by the target day's hourly UTC instants (23, 24 or 25 rows)."""
    idx = day_index(target_day)
    if cutoff > idx[0]:
        raise ValueError(f"cut-off {cutoff} is not before the target day {target_day}")
    cols = _calendar_block(target_day, idx, spec.calendar)
    cols.update(_lag_block(store.series("load_actual"), target_day, idx, cutoff))
    if spec.with_weather:
        cols.update(_weather_block(store, idx, spec))
    return pd.DataFrame(cols, index=idx)[spec.columns]
