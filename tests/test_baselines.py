from datetime import date

import numpy as np

from lastprog.backtest import feature_spec, run_backtest
from lastprog.models.baselines import residual_quantiles
from lastprog.timekeys import day_index


def test_naive_week_reproduces_the_lagged_series(fx_settings, fx_store):
    result = run_backtest(fx_settings, fx_store, date(2025, 10, 28), date(2025, 10, 30), ["naive_week"])
    load = fx_store.series("load_actual")
    for origin, (idx, q) in result.outputs["naive_week"].items():
        target = date.fromordinal(origin.toordinal() + 1)
        lagged = load.reindex(day_index(date.fromordinal(target.toordinal() - 7))).to_numpy()
        median_col = list(np.round(result.taus, 2)).index(0.5)
        resid_median = q[:, median_col] - lagged
        assert np.allclose(resid_median, resid_median[0])  # point + one constant residual quantile
        assert len(idx) == len(lagged)


def test_quantiles_are_monotone(fx_settings, fx_store):
    result = run_backtest(
        fx_settings, fx_store, date(2025, 10, 28), date(2025, 10, 30), ["naive_week", "naive_day", "mstl_ets"]
    )
    for by_origin in result.outputs.values():
        for _idx, q in by_origin.values():
            assert np.all(np.diff(q, axis=1) >= 0)


def test_residual_quantiles_without_history_are_nan():
    q = residual_quantiles(np.array([1.0, 2.0]), np.array([np.nan]), np.array([0.1, 0.5, 0.9]))
    assert np.isnan(q).all()


def test_feature_spec_rejects_one_day_weather_offset(fx_settings):
    import pytest

    from lastprog.features import FeatureSpec

    spec = feature_spec(fx_settings, False)
    with pytest.raises(ValueError, match="leaks"):
        FeatureSpec(calendar=spec.calendar, weather_offset_days=1)
