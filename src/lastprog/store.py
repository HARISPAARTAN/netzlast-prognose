"""Parquet store: observations (SMARD series) and weather (Open-Meteo Previous Runs), UTC timestamps.

observations.parquet: series, filter_id, region, ts_utc, value, chunk_ts_ms, fetched_at_utc;
unique (series, region, ts_utc). weather.parquet: city, ts_utc, variable, offset_days, model, value,
fetched_at_utc; unique (city, ts_utc, variable, offset_days, model). Nulls stay nulls, never zero.

fetched_at_utc is the UTC time (seconds) at which a row's value was first stored or last changed; upsert
stamps new rows itself, keeps the stamp of rows whose value is unchanged and never leaves a NaT.

Time semantics. Observations: ts_utc is the START of the hour, the value covers [t, t+1 h) (SMARD stamps).
Weather (Open-Meteo, hourly, timezone GMT): instantaneous variables such as temperature_2m are the value AT
ts_utc, but shortwave_radiation is the MEAN OF THE PRECEDING HOUR, i.e. it covers (t-1 h, t]. A feature that
joins radiation to the load hour [t, t+1 h) must shift it by one hour (use the value stamped t+1 h) or state
the convention explicitly. The stored values are not shifted. See docs/data-notes.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .smard import parse_chunk_file

OBS_COLUMNS = ["series", "filter_id", "region", "ts_utc", "value", "chunk_ts_ms", "fetched_at_utc"]
OBS_KEY = ["series", "region", "ts_utc"]
WX_COLUMNS = ["city", "ts_utc", "variable", "offset_days", "model", "value", "fetched_at_utc"]
WX_KEY = ["city", "ts_utc", "variable", "offset_days", "model"]
SERIES_BY_FILTER = {410: "load_actual", 411: "load_tso_forecast", 4169: "price_da"}


def _empty(columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in columns})
    df["ts_utc"] = pd.Series(dtype="datetime64[us, UTC]")
    df["value"] = pd.Series(dtype="float64")
    return df


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("s")


def _normalise(df: pd.DataFrame, columns: list[str], key: list[str]) -> pd.DataFrame:
    df = df.copy()
    if "fetched_at_utc" not in df:
        df["fetched_at_utc"] = _now()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True).astype("datetime64[us, UTC]")
    df["fetched_at_utc"] = pd.to_datetime(df["fetched_at_utc"], utc=True).astype("datetime64[us, UTC]")
    df["value"] = df["value"].astype("float64")
    df = df[columns].drop_duplicates(subset=key, keep="last")
    return df.sort_values(key, kind="mergesort").reset_index(drop=True)


def _unchanged(new: pd.DataFrame, old: pd.DataFrame, key: list[str]) -> pd.Series:
    """True for rows of `new` whose key exists in `old` with the same value (NaN equals NaN)."""
    joined = new[key + ["value"]].merge(
        old[key + ["value"]].drop_duplicates(subset=key, keep="last"),
        on=key,
        how="left",
        suffixes=("", "_old"),
        indicator=True,
    )
    same = (joined["value"] == joined["value_old"]) | (joined["value"].isna() & joined["value_old"].isna())
    return pd.Series((joined["_merge"] == "both").to_numpy() & same.to_numpy(), index=new.index)


def upsert(path: Path, new: pd.DataFrame, columns: list[str], key: list[str]) -> pd.DataFrame:
    """Merge `new` into the Parquet file at `path`; newer rows win per key. Returns the merged frame.

    New rows are stamped with the current time (unless they carry their own fetched_at_utc) before they are
    concatenated. A row whose value is unchanged keeps the stamp already stored. Any NaT stamp left in the
    old file (written by the earlier version) is stamped with the current time, so a normal fetch repairs it.
    """
    path = Path(path)
    now = _now()
    new = new.copy()
    if "fetched_at_utc" not in new:
        new["fetched_at_utc"] = now
    new["ts_utc"] = pd.to_datetime(new["ts_utc"], utc=True).astype("datetime64[us, UTC]")
    new["fetched_at_utc"] = pd.to_datetime(new["fetched_at_utc"], utc=True).astype("datetime64[us, UTC]")
    if path.exists():
        old = pd.read_parquet(path)
        old["fetched_at_utc"] = old["fetched_at_utc"].fillna(now)
        new = new[~_unchanged(new, old, key).to_numpy()]
        merged = pd.concat([old, new], ignore_index=True)
    else:
        merged = new
    merged = _normalise(merged, columns, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    merged.to_parquet(part, index=False)
    part.replace(path)
    return merged


def repair_fetched_at(store_dir: Path) -> dict[str, int]:
    """One-off, idempotent repair of stores written before the stamp fix: stamp every NaT fetched_at_utc.

    The stamp is the repair time, an upper bound of the true fetch time (the original time is lost).
    Values are not touched, so the snapshot hash does not change. Returns the rows found per file.
    """
    fixed = {}
    for name, columns, key in (
        ("observations.parquet", OBS_COLUMNS, OBS_KEY),
        ("weather.parquet", WX_COLUMNS, WX_KEY),
    ):
        path = Path(store_dir) / name
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        fixed[name] = int(df["fetched_at_utc"].isna().sum())
        if fixed[name]:
            upsert(path, df.iloc[0:0], columns, key)
    return fixed


def snapshot_hash(df: pd.DataFrame, key: list[str]) -> str:
    """SHA-256 of the sorted content without fetched_at_utc, so a re-fetch of identical data keeps the hash."""
    cols = [c for c in df.columns if c != "fetched_at_utc"]
    body = df[cols].sort_values(key, kind="mergesort").reset_index(drop=True)
    hashed = pd.util.hash_pandas_object(body, index=False).to_numpy()
    return hashlib.sha256(hashed.tobytes()).hexdigest()


@dataclass
class Store:
    observations: pd.DataFrame
    weather: pd.DataFrame
    region: str = "DE"
    _series_cache: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, store_dir: Path, region: str = "DE") -> Store:
        store_dir = Path(store_dir)
        obs_path, wx_path = store_dir / "observations.parquet", store_dir / "weather.parquet"
        obs = pd.read_parquet(obs_path) if obs_path.exists() else _empty(OBS_COLUMNS)
        wx = pd.read_parquet(wx_path) if wx_path.exists() else _empty(WX_COLUMNS)
        return cls(observations=obs, weather=wx, region=region)

    @classmethod
    def from_chunk_dir(cls, chunk_dir: Path, region: str = "DE") -> Store:
        """Build an in-memory store from cached SMARD chunk files (used for the committed fixtures)."""
        frames = []
        for path in sorted(Path(chunk_dir).glob("*.json")):
            filter_id = int(path.stem.split("_")[0])
            frames.append(parse_chunk_file(path, SERIES_BY_FILTER[filter_id]))
        obs = pd.concat(frames, ignore_index=True)
        obs["fetched_at_utc"] = pd.Timestamp("2025-11-10T12:00:00Z")
        return cls(
            observations=_normalise(obs, OBS_COLUMNS, OBS_KEY), weather=_empty(WX_COLUMNS), region=region
        )

    def series(self, name: str) -> pd.Series:
        """Hourly float64 series indexed by ts_utc (sorted, unique) for this store's region."""
        if name not in self._series_cache:
            obs = self.observations
            sel = obs[(obs["series"] == name) & (obs["region"] == self.region)]
            s = pd.Series(
                sel["value"].to_numpy(dtype="float64"), index=pd.DatetimeIndex(sel["ts_utc"]), name=name
            )
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s.index = s.index.astype("datetime64[ns, UTC]")
            s.index.name = "ts_utc"
            self._series_cache[name] = s
        return self._series_cache[name]

    def last_observed(self, name: str = "load_actual") -> pd.Timestamp | None:
        s = self.series(name).dropna()
        return None if s.empty else s.index[-1]

    def weather_wide(self, offset_days: int) -> pd.DataFrame:
        """Weather values of one lead offset as a frame indexed by ts_utc with columns 'city|variable'."""
        key = ("wx", offset_days)
        if key not in self._series_cache:
            wx = self.weather[self.weather["offset_days"] == offset_days]
            if wx.empty:
                wide = pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC", name="ts_utc"))
            else:
                wx = wx.assign(col=wx["city"] + "|" + wx["variable"])
                wide = wx.pivot_table(index="ts_utc", columns="col", values="value", aggfunc="last")
                wide.index = pd.DatetimeIndex(wide.index).astype("datetime64[ns, UTC]")
            self._series_cache[key] = wide.sort_index()
        return self._series_cache[key]

    def snapshot(self) -> str:
        """Combined snapshot hash of observations and weather."""
        h = hashlib.sha256()
        h.update(snapshot_hash(self.observations, OBS_KEY).encode())
        if len(self.weather):
            h.update(snapshot_hash(self.weather, WX_KEY).encode())
        return h.hexdigest()

    def with_observations_masked(
        self, cutoff: pd.Timestamp, sentinel: float, series: str = "load_actual"
    ) -> Store:
        """Copy in which every `series` value at or after `cutoff` is replaced by `sentinel` (leak tests)."""
        obs = self.observations.copy()
        mask = (obs["ts_utc"] >= cutoff) & (obs["series"] == series)
        obs.loc[mask, "value"] = np.float64(sentinel)
        return Store(observations=obs, weather=self.weather.copy(), region=self.region)
