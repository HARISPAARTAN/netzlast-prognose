from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from lastprog.features import (
    CALENDAR_FEATURES,
    LAG_FEATURES,
    FeatureSpec,
    HolidayCalendar,
    build_features,
    city_weights_from_seed,
)
from lastprog.timekeys import cutoff_utc, day_index


@pytest.fixture(scope="module")
def calendar(settings):
    return HolidayCalendar.from_seed(settings.paths.seed)


def test_population_seed_has_16_laender(calendar):
    assert len(calendar.population) == 16
    assert calendar.total == 83_467_117


def test_fronleichnam_share_strictly_between_zero_and_one(calendar):
    share = calendar.share(date(2025, 6, 19))
    assert 0.0 < share < 1.0
    assert calendar.is_national(date(2025, 6, 19)) is False


def test_reformationstag_2017_was_national(calendar):
    assert calendar.is_national(date(2017, 10, 31))
    assert calendar.share(date(2017, 10, 31)) == 1.0
    assert calendar.share(date(2018, 10, 31)) < 1.0


def test_buss_und_bettag_only_sachsen(calendar):
    assert calendar.share(date(2025, 11, 19)) == calendar.population["SN"] / calendar.total


def test_bridge_day_after_christi_himmelfahrt(calendar):
    assert calendar.is_national(date(2025, 5, 29))  # Thursday
    assert calendar.is_bridge(date(2025, 5, 30))  # Friday
    assert not calendar.is_bridge(date(2025, 5, 28))
    assert not calendar.is_bridge(date(2025, 5, 31))  # Saturday


def test_city_weights_sum_to_one(settings):
    w = city_weights_from_seed(settings.paths.seed)
    assert len(w) == 8
    assert abs(sum(w.values()) - 1.0) < 1e-12


def test_feature_frame_shape_and_lags(fx_store, calendar):
    spec = FeatureSpec(calendar=calendar)
    target = date(2025, 10, 28)
    f = build_features(fx_store, target, cutoff_utc(date(2025, 10, 27)), spec)
    assert list(f.columns) == CALENDAR_FEATURES + LAG_FEATURES
    assert len(f) == 24
    load = fx_store.series("load_actual")
    # naive_week input: same local hour one week before the target.
    assert f["lag_d6"].tolist() == load.reindex(day_index(date(2025, 10, 21))).tolist()
    # D-1 (two days before the target) and its daily mean.
    d1 = load.reindex(day_index(date(2025, 10, 26))).to_numpy()  # 25-hour day
    assert f["d1_mean"].iloc[0] == pytest.approx(d1.mean())
    assert f["d1_max"].iloc[0] == d1.max()
    assert f["hol_share"].iloc[0] == 0.0


def test_dst_target_day_features(fx_store, calendar):
    spec = FeatureSpec(calendar=calendar)
    f = build_features(fx_store, date(2025, 10, 26), cutoff_utc(date(2025, 10, 25)), spec)
    assert len(f) == 25
    assert f["dst_day"].eq(1.0).all()
    assert f["hour"].tolist().count(2.0) == 2
    assert not f["lag_d6"].isna().any()


def test_reformationstag_regional_share_in_fixture_period(fx_store, calendar):
    spec = FeatureSpec(calendar=calendar)
    f = build_features(fx_store, date(2025, 10, 31), cutoff_utc(date(2025, 10, 30)), spec)
    assert 0.0 < f["hol_share"].iloc[0] < 0.5
    assert f["hol_share_next"].iloc[0] > 0.0  # Allerheiligen in BW, BY, NW, RP, SL


def test_cutoff_must_precede_target(fx_store, calendar):
    with pytest.raises(ValueError, match="not before"):
        build_features(
            fx_store, date(2025, 10, 28), pd.Timestamp("2025-10-28T12:00:00Z"), FeatureSpec(calendar)
        )


def test_missing_recent_data_gives_nan_lags_not_errors(fx_store, calendar):
    late = fx_store.with_observations_masked(pd.Timestamp("2025-11-05T23:00:00Z"), np.nan)
    f = build_features(late, date(2025, 11, 8), cutoff_utc(date(2025, 11, 7)), FeatureSpec(calendar))
    assert f["lag_d1"].isna().all()
    assert not f["lag_d6"].isna().any()


# Leak and weather tests added by the implementation (Task 3 review notes).


def test_no_load_leak_from_observations_at_or_after_cutoff(fx_store, calendar):
    """Replacing every observation from the cut-off on by a sentinel must not change a single feature."""
    spec = FeatureSpec(calendar=calendar)
    for target in (date(2025, 10, 28), date(2025, 10, 26), date(2025, 10, 31)):
        cutoff = cutoff_utc(target - timedelta(days=1))
        clean = build_features(fx_store, target, cutoff, spec)
        masked = build_features(fx_store.with_observations_masked(cutoff, 1e9), target, cutoff, spec)
        pd.testing.assert_frame_equal(clean, masked)


def test_reference_forecast_is_not_a_feature(fx_store, calendar):
    spec = FeatureSpec(calendar=calendar)
    target = date(2025, 10, 28)
    cutoff = cutoff_utc(date(2025, 10, 27))
    base = build_features(fx_store, target, cutoff, spec)
    altered = fx_store.with_observations_masked(
        pd.Timestamp("2000-01-01T00:00:00Z"), 1e9, "load_tso_forecast"
    )
    pd.testing.assert_frame_equal(base, build_features(altered, target, cutoff, spec))


def test_spec_rejects_short_weather_offset_and_missing_weights(calendar):
    with pytest.raises(ValueError, match="two days"):
        FeatureSpec(calendar=calendar, weather_offset_days=1)
    with pytest.raises(ValueError, match="city weights"):
        FeatureSpec(calendar=calendar, with_weather=True)


def _weather_store(fx_store, idx):
    """Copy of the fixture store with synthetic two-city weather (offset 2): temperature = 10 + hour index,
    radiation = 1000 + hour index, so the stamp that was read can be recovered from the value."""
    n = np.arange(len(idx), dtype="float64")
    rows = []
    for city, shift in (("A", 0.0), ("B", 10.0)):
        for variable, base in (("temperature_2m", 10.0), ("shortwave_radiation", 1000.0)):
            rows.append(
                pd.DataFrame(
                    {
                        "city": city,
                        "ts_utc": idx,
                        "variable": variable,
                        "offset_days": 2,
                        "model": "best_match",
                        "value": base + n + shift,
                        "fetched_at_utc": pd.Timestamp("2025-11-10T12:00:00Z"),
                    }
                )
            )
    from lastprog.store import Store

    return Store(
        observations=fx_store.observations, weather=pd.concat(rows, ignore_index=True), region=fx_store.region
    )


def test_weather_features_weights_and_radiation_shift(fx_store, calendar):
    target = date(2025, 10, 28)
    idx = pd.date_range("2025-10-20T00:00:00Z", "2025-11-02T00:00:00Z", freq="h", name="ts_utc")
    store = _weather_store(fx_store, idx)
    spec = FeatureSpec(calendar=calendar, with_weather=True, city_weights={"A": 0.75, "B": 0.25})
    f = build_features(store, target, cutoff_utc(date(2025, 10, 27)), spec)
    day = day_index(target)
    pos = np.array([idx.get_loc(t) for t in day], dtype="float64")
    # Temperature is instantaneous: the value stamped at the target hour itself.
    assert f["wx_temp"].to_numpy() == pytest.approx(10.0 + pos + 0.25 * 10.0)
    # Radiation is the mean of the preceding hour: the load hour [t, t+1h) takes the value stamped t+1h.
    assert f["wx_ssr"].to_numpy() == pytest.approx(1000.0 + pos + 1.0 + 0.25 * 10.0)
    assert (f["wx_hdh"] == np.maximum(0.0, 15.0 - f["wx_temp"])).all()
    assert (f["wx_cdh"] == np.maximum(0.0, f["wx_temp"] - 22.0)).all()
    assert list(f.columns) == spec.columns


def test_weather_features_nan_when_weather_missing(fx_store, calendar):
    idx = pd.date_range("2025-10-20T00:00:00Z", "2025-10-27T12:00:00Z", freq="h", name="ts_utc")
    store = _weather_store(fx_store, idx)
    spec = FeatureSpec(calendar=calendar, with_weather=True, city_weights={"A": 0.5, "B": 0.5})
    f = build_features(store, date(2025, 10, 28), cutoff_utc(date(2025, 10, 27)), spec)
    assert f["wx_temp"].isna().all() and f["wx_ssr"].isna().all()
