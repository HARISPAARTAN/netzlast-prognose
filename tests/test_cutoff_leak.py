"""Every load value at or after the cut-off is replaced by a huge sentinel; nothing issued before may change."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pandas.testing as pdt

from lastprog.backtest import feature_spec, run_backtest
from lastprog.features import FeatureSpec, build_features, city_weights_from_seed
from lastprog.store import WX_COLUMNS, Store
from lastprog.timekeys import cutoff_utc, day_index

SENTINEL = 1e12
LEAK_MODELS = ["naive_week", "naive_day", "mstl_ets", "lgbm_qr", "lgbm_cqr", "lgbm_cqr_dp", "lgbm_aci"]


def test_features_are_bit_identical_under_masking(fx_settings, fx_store):
    spec = feature_spec(fx_settings, False)
    for origin in (date(2025, 10, 25), date(2025, 11, 2), date(2025, 11, 7)):
        cutoff = cutoff_utc(origin)
        masked = fx_store.with_observations_masked(cutoff, SENTINEL)
        clean = build_features(fx_store, origin + timedelta(days=1), cutoff, spec)
        dirty = build_features(masked, origin + timedelta(days=1), cutoff, spec)
        pdt.assert_frame_equal(clean, dirty, check_exact=True)


def test_forecasts_and_conformal_window_are_bit_identical(fx_settings, fx_store):
    last = date(2025, 11, 4)
    masked = fx_store.with_observations_masked(cutoff_utc(last), SENTINEL)
    a = run_backtest(fx_settings, fx_store, date(2025, 11, 1), last, LEAK_MODELS)
    b = run_backtest(fx_settings, masked, date(2025, 11, 1), last, LEAK_MODELS)
    for model in LEAK_MODELS:
        for origin, (idx, q) in a.outputs[model].items():
            idx_b, q_b = b.outputs[model][origin]
            assert idx.equals(idx_b)
            np.testing.assert_array_equal(q, q_b, err_msg=f"{model} {origin}")


def test_model_fit_at_a_month_start_origin_does_not_see_day_d(fx_settings, fx_store):
    """Single origin 2025-11-01: LightGBM is (re)fitted there. A sentinel at and after its cut-off must not
    change forecasts, so the training rows may not reach into day D (Task 4 review I-1)."""
    origin = date(2025, 11, 1)
    masked = fx_store.with_observations_masked(cutoff_utc(origin), SENTINEL)
    models = ["lgbm_qr", "lgbm_cqr"]
    a = run_backtest(fx_settings, fx_store, origin, origin, models)
    b = run_backtest(fx_settings, masked, origin, origin, models)
    assert a.fits["lgbm_qr"] == ["2025-10-24", "2025-11-01"]  # warm-up fit plus the month-start refit
    for model in models:
        np.testing.assert_array_equal(a.outputs[model][origin][1], b.outputs[model][origin][1], err_msg=model)


def test_model_fit_at_the_first_origin_of_a_run_does_not_see_day_d(fx_settings, fx_store):
    origin = date(2025, 10, 25)
    masked = fx_store.with_observations_masked(cutoff_utc(origin), SENTINEL)
    a = run_backtest(fx_settings, fx_store, origin, origin, ["lgbm_qr"])
    b = run_backtest(fx_settings, masked, origin, origin, ["lgbm_qr"])
    assert a.fits["lgbm_qr"] == [origin.isoformat()]
    np.testing.assert_array_equal(a.outputs["lgbm_qr"][origin][1], b.outputs["lgbm_qr"][origin][1])


def test_sentinel_would_be_detected(fx_settings, fx_store):
    """Control: masking one hour *before* the cut-off must change the forecast, or the test proves nothing."""
    last = date(2025, 11, 4)
    early = fx_store.with_observations_masked(cutoff_utc(last) - pd.Timedelta(hours=1), SENTINEL)
    a = run_backtest(fx_settings, fx_store, last, last, ["naive_day"])
    b = run_backtest(fx_settings, early, last, last, ["naive_day"])
    assert not np.array_equal(a.outputs["naive_day"][last][1], b.outputs["naive_day"][last][1])


def _weather_store(fx_store, idx: pd.DatetimeIndex, cities: list[str], day1_value: float) -> Store:
    rows = []
    for city in cities:
        for var in ("temperature_2m", "shortwave_radiation"):
            for offset, value in ((2, 10.0), (1, day1_value)):
                rows.append(
                    pd.DataFrame(
                        {
                            "city": city,
                            "ts_utc": idx,
                            "variable": var,
                            "offset_days": offset,
                            "model": "best_match",
                            "value": value,
                            "fetched_at_utc": pd.Timestamp("2026-01-01T00:00:00Z"),
                        }
                    )
                )
    wx = pd.concat(rows, ignore_index=True)[WX_COLUMNS]
    return Store(observations=fx_store.observations, weather=wx, region="DE")


def test_weather_features_only_use_the_two_day_offset(fx_settings, fx_store):
    weights = city_weights_from_seed(fx_settings.paths.seed)
    spec = FeatureSpec(feature_spec(fx_settings, False).calendar, True, 2, weights)
    target = date(2025, 11, 3)
    idx = day_index(target)
    clean = build_features(
        _weather_store(fx_store, idx, list(weights), 99.0), target, cutoff_utc(date(2025, 11, 2)), spec
    )
    dirty = build_features(
        _weather_store(fx_store, idx, list(weights), SENTINEL), target, cutoff_utc(date(2025, 11, 2)), spec
    )
    pdt.assert_frame_equal(clean, dirty, check_exact=True)
    assert clean["wx_temp"].eq(10.0).all() and clean["wx_hdh"].eq(5.0).all()
