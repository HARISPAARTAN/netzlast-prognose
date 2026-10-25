import numpy as np
import pandas as pd

from lastprog.store import OBS_COLUMNS, OBS_KEY, Store, repair_fetched_at, upsert


def _rows(values, start="2025-10-19T22:00:00Z", series="load_actual"):
    ts = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.DataFrame(
        {"series": series, "filter_id": 410, "region": "DE", "ts_utc": ts, "value": values, "chunk_ts_ms": 1}
    )


def test_upsert_newer_rows_win_and_nulls_survive(tmp_path):
    path = tmp_path / "observations.parquet"
    upsert(path, _rows([1.0, np.nan, 3.0]), OBS_COLUMNS, OBS_KEY)
    merged = upsert(path, _rows([2.0], start="2025-10-19T23:00:00Z"), OBS_COLUMNS, OBS_KEY)
    assert merged["value"].tolist() == [1.0, 2.0, 3.0]
    again = upsert(path, _rows([np.nan], start="2025-10-20T01:00:00Z"), OBS_COLUMNS, OBS_KEY)
    assert np.isnan(again["value"].iloc[-1])
    assert str(pd.read_parquet(path)["ts_utc"].dtype) == "datetime64[us, UTC]"


def test_fixture_store_series_and_snapshot(fx_store):
    s = fx_store.series("load_actual")
    assert s.index.is_monotonic_increasing and s.index.is_unique
    assert s.index[0] == pd.Timestamp("2025-08-31T22:00:00Z")
    assert s.index[-1] == pd.Timestamp("2025-11-09T22:00:00Z")
    assert len(s) == 70 * 24 + 1  # ten weeks, one 25-hour day
    assert len(fx_store.series("load_tso_forecast")) == len(s)
    assert fx_store.last_observed() == pd.Timestamp("2025-11-09T22:00:00Z")
    assert fx_store.snapshot() == fx_store.snapshot()


def test_snapshot_ignores_fetch_time(tmp_path):
    a = _rows([1.0, 2.0]).assign(fetched_at_utc=pd.Timestamp("2025-01-01T00:00:00Z"))
    b = a.assign(fetched_at_utc=pd.Timestamp("2026-01-01T00:00:00Z"))
    sa = Store(upsert(tmp_path / "a.parquet", a, OBS_COLUMNS, OBS_KEY), pd.DataFrame())
    sb = Store(upsert(tmp_path / "b.parquet", b, OBS_COLUMNS, OBS_KEY), pd.DataFrame())
    assert sa.snapshot() == sb.snapshot()


def test_masking_only_touches_load_after_cutoff(fx_store):
    cutoff = pd.Timestamp("2025-11-01T23:00:00Z")
    masked = fx_store.with_observations_masked(cutoff, 1e12)
    s = masked.series("load_actual")
    assert (s[s.index >= cutoff] == 1e12).all()
    assert (s[s.index < cutoff] == fx_store.series("load_actual")[s.index < cutoff]).all()
    assert masked.series("load_tso_forecast").equals(fx_store.series("load_tso_forecast"))


def test_upsert_stamps_new_rows_and_never_writes_nat(tmp_path):
    path = tmp_path / "observations.parquet"
    first = upsert(path, _rows([1.0, 2.0]), OBS_COLUMNS, OBS_KEY)
    assert first["fetched_at_utc"].notna().all()
    stamp = pd.Timestamp("2025-01-01T00:00:00Z")
    old = pd.read_parquet(path).assign(fetched_at_utc=stamp)
    old.to_parquet(path, index=False)
    # Re-run with identical rows plus one new and one changed row: no NaT anywhere.
    rerun = upsert(path, _rows([1.0, 5.0, 3.0]), OBS_COLUMNS, OBS_KEY)
    assert rerun["fetched_at_utc"].notna().all()
    stamps = dict(zip(rerun["value"], rerun["fetched_at_utc"], strict=True))
    assert stamps[1.0] == stamp  # unchanged row keeps its stamp
    assert stamps[5.0] > stamp and stamps[3.0] > stamp  # changed and new rows are stamped now
    # A different series written later (the load_tso_forecast case) is stamped too.
    other = upsert(path, _rows([7.0], series="load_tso_forecast"), OBS_COLUMNS, OBS_KEY)
    assert other["fetched_at_utc"].notna().all()
    assert pd.read_parquet(path)["fetched_at_utc"].notna().all()


def test_repair_fetched_at_is_idempotent_and_keeps_values(tmp_path):
    path = tmp_path / "observations.parquet"
    upsert(path, _rows([1.0, np.nan, 3.0]), OBS_COLUMNS, OBS_KEY)
    broken = pd.read_parquet(path)
    broken["fetched_at_utc"] = pd.Series(pd.NaT, index=broken.index, dtype="datetime64[us, UTC]")
    broken.to_parquet(path, index=False)
    before = Store.load(tmp_path).snapshot()
    assert repair_fetched_at(tmp_path) == {"observations.parquet": 3}
    assert pd.read_parquet(path)["fetched_at_utc"].notna().all()
    assert repair_fetched_at(tmp_path) == {"observations.parquet": 0}
    assert Store.load(tmp_path).snapshot() == before
