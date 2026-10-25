"""Live job on the fixture period: issue, refuse to overwrite, score once observed, freshness log."""

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from lastprog.live import append_freshness, entry_path, issue, score_pending
from lastprog.monitor import psi, psi_reference, read_log, rolling_live_metrics
from lastprog.service import DataNotReady, Forecaster
from lastprog.timekeys import day_index


@pytest.fixture()
def fc(fx_settings, fx_store, demo_model_dir):
    return Forecaster(replace(fx_settings, mode="full"), fx_store, demo_model_dir)


def test_issue_score_and_freshness(fc, tmp_path):
    now = pd.Timestamp("2025-11-03T07:00:00Z")
    path = issue(fc, tmp_path, now)
    assert path == entry_path(tmp_path, pd.Timestamp("2025-11-04").date())
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert set(entry["models"]) == {"lgbm_cqr", "naive_week"}
    assert entry["run"]["cutoff_used_utc"] == "2025-11-02T23:00:00Z"
    assert entry["run"]["missing_hours_before_cutoff"] == 0
    assert set(entry["run"]["psi"]) == {"lag_d1", "lag_d6", "d1_mean", "d7_mean"}
    assert issue(fc, tmp_path, now) is None  # never overwritten
    scored = score_pending(fc, tmp_path, pd.Timestamp("2025-11-06T07:00:00Z"))
    assert scored == [path]
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert len(entry["scored"]["actual"]) == 24 and len(entry["scored"]["reference"]) == 24
    assert set(entry["scored"]["metrics"]) == {"lgbm_cqr", "naive_week", "tso_reference"}
    append_freshness(tmp_path, now, fc.store.last_observed())
    header = (tmp_path / "freshness.csv").read_text().splitlines()[0]
    assert header == "run_time_utc,data_last_ts_utc,lag_hours"
    df = rolling_live_metrics(read_log(tmp_path))
    assert len(df) == 1 and df["crps_roll"].iloc[0] == entry["scored"]["metrics"]["lgbm_cqr"]["crps"]


def test_late_publication_is_tolerated_up_to_the_limit(fx_settings, fx_store, demo_model_dir, tmp_path):
    late = fx_store.with_observations_masked(pd.Timestamp("2025-11-02T12:00:00Z"), np.nan)
    late.observations = late.observations.dropna(subset=["value"])
    fc = Forecaster(replace(fx_settings, mode="full"), late, demo_model_dir)
    now = pd.Timestamp("2025-11-03T07:00:00Z")
    assert issue(fc, tmp_path, now, max_missing_hours=24) is not None
    with pytest.raises(DataNotReady):
        fc.forecast(pd.Timestamp("2025-11-04").date(), "lgbm_cqr", max_missing_hours=0)


def test_psi_flags_a_shift():
    rng = np.random.default_rng(0)
    ref = psi_reference(rng.normal(0, 1, 5000))
    assert psi(ref, rng.normal(0, 1, 2000)) < 0.05
    assert psi(ref, rng.normal(1.5, 1, 2000)) > 0.2


def test_cli_skips_with_a_logged_reason_when_smard_is_late(
    fx_settings, fx_store, demo_model_dir, tmp_path, monkeypatch
):
    """The fixture store ends in 2025, so for the real clock the data is far too old: no entry, no fabrication."""
    from typer.testing import CliRunner

    from lastprog import api
    from lastprog.cli import app

    fc = Forecaster(replace(fx_settings, mode="full"), fx_store, demo_model_dir)
    monkeypatch.setattr(api, "build_forecaster", lambda settings=None: fc)
    result = CliRunner().invoke(app, ["live", "--log-dir", str(tmp_path), "--no-fetch"])
    assert result.exit_code == 0, result.output
    assert "::warning::no forecast issued: store has load data up to 2025-11-09T22:00:00Z" in result.output
    assert not list(tmp_path.glob("[0-9][0-9][0-9][0-9]/*/*.json"))
    assert (tmp_path / "freshness.csv").exists()


TARGET = pd.Timestamp("2025-11-04").date()


def _scored_entry(fc, log_dir):
    path = issue(fc, log_dir, pd.Timestamp("2025-11-03T07:00:00Z"))
    assert score_pending(fc, log_dir, pd.Timestamp("2025-11-06T07:00:00Z")) == [path]
    return json.loads(path.read_text(encoding="utf-8"))


def test_stored_scores_equal_an_independent_computation(fc, fx_store, tmp_path):
    """Actuals, reference and every metric are recomputed here from the store and the logged quantiles."""
    entry = _scored_entry(fc, tmp_path)
    idx = day_index(TARGET)
    y = fx_store.series("load_actual").reindex(idx).to_numpy("float64")
    ref = fx_store.series("load_tso_forecast").reindex(idx).to_numpy("float64")
    scored = entry["scored"]
    assert scored["actual"] == pytest.approx(y, abs=0.01)  # an actual shifted by one hour fails here
    assert scored["reference"] == pytest.approx(ref, abs=0.01)
    for name in ("lgbm_cqr", "naive_week"):
        doc = entry["models"][name]
        q = np.array([p["quantiles"] for p in doc["points"]])
        taus = np.array(doc["quantile_levels"])
        err = y[:, None] - q
        pinball = np.maximum(taus * err, (taus - 1) * err)
        med = np.array([p["median"] for p in doc["points"]])
        got = scored["metrics"][name]
        assert got["crps"] == pytest.approx((2 * pinball.sum(axis=1) / (len(taus) + 1)).mean(), abs=1e-3)
        assert got["mae"] == pytest.approx(np.abs(y - med).mean(), abs=1e-3)
        assert got["mae"] > 0
        for level, key in (("0.5", "cov_50"), ("0.8", "cov_80"), ("0.9", "cov_90")):
            lo, hi = np.array([p["intervals"][level] for p in doc["points"]]).T
            assert got[key] == pytest.approx(((y >= lo) & (y <= hi)).mean(), abs=1e-3)
    # The operators' reference is scored against the actuals, not against itself or the actuals' own mean.
    assert scored["metrics"]["tso_reference"]["mae"] == pytest.approx(np.abs(y - ref).mean(), abs=1e-3)
    assert scored["metrics"]["tso_reference"]["mae"] > 0


def test_a_partly_published_day_stays_unscored_until_complete(fc, fx_settings, fx_store, tmp_path):
    path = issue(fc, tmp_path, pd.Timestamp("2025-11-03T07:00:00Z"))
    partial = fx_store.with_observations_masked(pd.Timestamp("2025-11-04T12:00:00Z"), np.nan)
    fc_partial = Forecaster(fc.settings, partial, None)
    fc_partial.manifest, fc_partial.model, fc_partial.calibration = fc.manifest, fc.model, fc.calibration
    before = path.read_text(encoding="utf-8")
    assert score_pending(fc_partial, tmp_path, pd.Timestamp("2025-11-06T07:00:00Z")) == []
    assert path.read_text(encoding="utf-8") == before
    assert json.loads(before)["scored"] is None
    # Once the rest of the day is published the entry is scored, with finite metrics.
    assert score_pending(fc, tmp_path, pd.Timestamp("2025-11-06T08:00:00Z")) == [path]
    metrics = json.loads(path.read_text(encoding="utf-8"))["scored"]["metrics"]
    assert all(np.isfinite(v) for m in metrics.values() for v in m.values())


def test_an_entry_is_scored_once(fc, tmp_path):
    path = issue(fc, tmp_path, pd.Timestamp("2025-11-03T07:00:00Z"))
    assert score_pending(fc, tmp_path, pd.Timestamp("2025-11-06T07:00:00Z")) == [path]
    first = path.read_text(encoding="utf-8")
    assert score_pending(fc, tmp_path, pd.Timestamp("2025-11-07T07:00:00Z")) == []
    assert path.read_text(encoding="utf-8") == first


def test_the_issue_day_is_the_berlin_date_late_in_the_evening_utc(fc, tmp_path):
    """23:30 UTC is already 00:30 on the next day in Berlin: that day is the issue day, its successor the target."""
    path = issue(fc, tmp_path, pd.Timestamp("2025-11-03T23:30:00Z"))
    assert path == entry_path(tmp_path, pd.Timestamp("2025-11-05").date())
    assert json.loads(path.read_text(encoding="utf-8"))["run"]["cutoff_used_utc"] == "2025-11-03T23:00:00Z"


def test_drift_window_is_a_year_and_flags_a_shifted_store(fc, fx_store, tmp_path, monkeypatch):
    from lastprog import live
    from lastprog.store import Store

    assert live.DRIFT_WINDOW_DAYS == 365 and live.HISTORY_DAYS >= live.DRIFT_WINDOW_DAYS + 13
    calls = []
    real = live.build_features
    monkeypatch.setattr(live, "build_features", lambda *a, **k: calls.append(a[1]) or real(*a, **k))
    path = issue(fc, tmp_path, pd.Timestamp("2025-11-03T07:00:00Z"))
    run = json.loads(path.read_text(encoding="utf-8"))["run"]
    assert run["psi_window_days"] == 365 and len(calls) == 365
    assert len(set(calls)) == 365 and max(calls) == pd.Timestamp("2025-11-03").date()
    obs = fx_store.observations.copy()
    obs.loc[obs["series"] == "load_actual", "value"] *= 1.5
    shifted = Forecaster(fc.settings, Store(obs, fx_store.weather), None)
    shifted.manifest, shifted.model, shifted.calibration = fc.manifest, fc.model, fc.calibration
    drift = live._drift(shifted, pd.Timestamp("2025-11-03").date())
    assert max(drift.values()) > 0.2
