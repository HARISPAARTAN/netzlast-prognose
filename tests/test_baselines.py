from datetime import date, timedelta

import numpy as np

from lastprog.backtest import feature_spec, run_backtest
from lastprog.models.baselines import residual_quantiles
from lastprog.timekeys import cutoff_utc, day_index


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


def test_lgbm_quantiles_are_monotone_for_every_row(fx_settings, fx_store):
    models = ["lgbm_qr", "lgbm_cqr", "lgbm_cqr_dp", "lgbm_aci"]
    result = run_backtest(fx_settings, fx_store, date(2025, 10, 28), date(2025, 10, 31), models)
    for model in models:
        for origin, (_idx, q) in result.outputs[model].items():
            assert np.isfinite(q).all(), f"{model} {origin}"
            assert (np.diff(q, axis=1) >= 0).all(), f"{model} {origin}"


def test_lgbm_rearrangement_removes_crossings(fx_settings, fx_store):
    """The raw boosters cross on the fixtures; predict_frame must return the sorted grid."""
    from lastprog.backtest import FeatureCache
    from lastprog.models.lgbm import LgbmQuantile

    spec = feature_spec(fx_settings, False)
    cache = FeatureCache(fx_store, spec, fx_settings.cutoff_rule)
    origin = date(2025, 11, 1)
    X, y = cache.training_frame(origin, cutoff_utc(origin), fx_settings.backtest.train_window_days)
    m = fx_settings.model
    model = LgbmQuantile("lgbm_qr", np.array(m.quantiles), m.lgbm, m.seed, m.num_threads, spec.columns)
    model.fit(X, y)
    features = cache.get(origin + timedelta(days=1))
    raw = np.column_stack([b.predict(features[spec.columns].to_numpy("float64")) for b in model.boosters])
    assert (np.diff(raw, axis=1) < 0).any(), "fixture no longer produces crossings; pick a harder case"
    out = model.predict_frame(features)
    assert (np.diff(out, axis=1) >= 0).all()
    np.testing.assert_array_equal(out, np.sort(raw, axis=1))
