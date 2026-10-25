"""Tuning picks the lowest validation pinball loss; the frozen config matches the committed tuning result."""

import json
from dataclasses import replace

import pytest

from lastprog import tuning


def test_tune_on_fixture_period(fx_settings, fx_store, tmp_path, monkeypatch):
    grid = [
        {"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 20, "min_child_samples": 20},
        {"num_leaves": 15, "learning_rate": 0.1, "n_estimators": 40, "min_child_samples": 20},
    ]
    monkeypatch.setattr(tuning, "TUNING_GRID", grid)
    s = replace(fx_settings, backtest=replace(fx_settings.backtest, validation=fx_settings.backtest.fixtures))
    out = tuning.tune(s, fx_store, tmp_path / "tuning.json")
    assert len(out["grid"]) == 2
    assert out["best"]["pinball"] == min(r["pinball"] for r in out["grid"])
    assert json.loads((tmp_path / "tuning.json").read_text())["best"] == out["best"]


def test_grid_has_at_most_twelve_settings():
    assert len(tuning.TUNING_GRID) <= 12


def test_frozen_config_matches_tuning_result(settings):
    path = settings.paths.results / "tuning-v1.json"
    if not path.exists():
        pytest.skip("tuning-v1.json is written in Task 5")
    best = json.loads(path.read_text(encoding="utf-8"))["best"]
    lgbm = settings.model.lgbm
    for key in ("num_leaves", "learning_rate", "n_estimators", "min_child_samples"):
        assert getattr(lgbm, key) == best[key], key
