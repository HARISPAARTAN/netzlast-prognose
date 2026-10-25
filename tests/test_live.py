"""Live job on the fixture period: issue, refuse to overwrite, score once observed, freshness log."""

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from lastprog.live import append_freshness, entry_path, issue, score_pending
from lastprog.monitor import psi, psi_reference, read_log, rolling_live_metrics
from lastprog.service import DataNotReady, Forecaster


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
