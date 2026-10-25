from datetime import date

import pytest

from lastprog.config import load_settings


def test_defaults_match_the_spec(settings):
    assert settings.data.region == "DE"
    assert settings.data.load_filter == 410
    assert settings.data.reference_filter == 411
    assert settings.data.resolution == "hour"
    assert settings.backtest.validation == (date(2023, 10, 1), date(2024, 9, 30))
    assert settings.backtest.test == (date(2024, 10, 1), date(2026, 9, 30))
    assert settings.backtest.train_window_days == 1095
    assert settings.backtest.dm_lag == 7
    assert len(settings.model.quantiles) == 19
    assert settings.model.quantiles[0] == 0.05 and settings.model.quantiles[-1] == 0.95
    assert settings.model.seed == 20261025
    assert settings.conformal.window_origins == 56
    assert settings.conformal.levels == (0.5, 0.8, 0.9)
    assert settings.weather.enabled is False
    assert settings.weather.offset_days == 2
    assert settings.offline is True


def test_fixture_overrides(fx_settings):
    assert fx_settings.is_fixtures
    assert fx_settings.model.num_threads == 1
    assert fx_settings.conformal.window_origins == 7
    assert fx_settings.backtest.train_window_days == 28
    assert fx_settings.backtest.fixtures == (date(2025, 10, 25), date(2025, 11, 7))


def test_data_dir_and_mode_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("LASTPROG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LASTPROG_MODE", "demo")
    s = load_settings()
    assert s.paths.store == tmp_path.resolve() / "store"
    assert s.paths.raw == tmp_path.resolve() / "raw"
    assert s.paths.models == tmp_path.resolve() / "models"
    assert s.mode == "demo"


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("LASTPROG_MODE", "staging")
    with pytest.raises(ValueError, match="LASTPROG_MODE"):
        load_settings()
