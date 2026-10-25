from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from lastprog.features import (
    CALENDAR_FEATURES,
    LAG_FEATURES,
    RADIATION_SHIFT,
    FeatureSpec,
    HolidayCalendar,
    build_features,
    city_weights_from_seed,
)
from lastprog.store import OBS_COLUMNS, Store
from lastprog.timekeys import cutoff_utc, daterange, day_index, hours_in_day


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


# Lag values pinned against independently built expectations (Task 3 fix report, review I-1).


def _day(load: pd.Series, d: date) -> np.ndarray:
    """The load values of local day `d` in UTC order (23, 24 or 25 values)."""
    return load.reindex(day_index(d)).to_numpy("float64")


def _synthetic_store(fx_store, start: str, end: str) -> Store:
    """Hourly load for a stretch without the fixture's data: value = hours since `start`, unique per hour,
    so the instant that a lag read can be recovered from the value."""
    idx = pd.date_range(start, end, freq="h", tz="UTC", name="ts_utc")
    obs = pd.DataFrame(
        {
            "series": "load_actual",
            "filter_id": 410,
            "region": "DE",
            "ts_utc": idx,
            "value": np.arange(len(idx), dtype="float64") + 1000.0,
            "chunk_ts_ms": 0,
            "fetched_at_utc": pd.Timestamp("2025-11-10T12:00:00Z"),
        }
    )[OBS_COLUMNS]
    return Store(observations=obs, weather=fx_store.weather, region="DE")


def _lags(store, calendar, target: date) -> pd.DataFrame:
    return build_features(store, target, cutoff_utc(target - timedelta(days=1)), FeatureSpec(calendar))


def test_all_four_lags_and_aggregates_on_a_normal_day(fx_store, calendar):
    load = fx_store.series("load_actual")
    target = date(2025, 11, 5)  # lag days 11-03, 11-02, 10-29, 10-22 are 24-hour days
    f = _lags(fx_store, calendar, target)
    for name, days_back in (("lag_d1", 2), ("lag_d2", 3), ("lag_d6", 7), ("lag_d13", 14)):
        expected = _day(load, target - timedelta(days=days_back))
        assert len(expected) == 24
        assert f[name].to_numpy() == pytest.approx(expected, abs=0), name
    d1 = _day(load, target - timedelta(days=2))
    d8 = _day(load, target - timedelta(days=9))
    week = np.concatenate([_day(load, target - timedelta(days=k)) for k in range(2, 9)])
    assert f["d1_mean"].iloc[0] == pytest.approx(d1.mean())
    assert f["d1_max"].iloc[0] == d1.max()
    assert f["d7_mean"].iloc[0] == pytest.approx(week.mean())
    assert f["ratio_d1_d8"].iloc[0] == pytest.approx(d1.mean() / d8.mean())
    # Three different numbers, so a swap or a shifted day cannot hide behind equal values.
    assert len({f["d1_mean"].iloc[0], f["d7_mean"].iloc[0], f["ratio_d1_d8"].iloc[0]}) == 3


def test_d7_mean_counts_every_hour_of_a_25_hour_day(fx_store, calendar):
    load = fx_store.series("load_actual")
    target = date(2025, 10, 28)  # D-1 .. D-7 = 10-26 (25 hours) .. 10-20
    f = _lags(fx_store, calendar, target)
    week = np.concatenate([_day(load, target - timedelta(days=k)) for k in range(2, 9)])
    assert len(week) == 24 * 6 + 25
    assert f["d7_mean"].iloc[0] == pytest.approx(week.mean())
    d8 = _day(load, target - timedelta(days=9))
    assert f["ratio_d1_d8"].iloc[0] == pytest.approx(_day(load, date(2025, 10, 26)).mean() / d8.mean())


@pytest.mark.parametrize(
    "target, name",
    [
        (date(2025, 10, 28), "lag_d1"),  # 2 days after the 25-hour day 2025-10-26
        (date(2025, 10, 29), "lag_d2"),
        (date(2025, 11, 2), "lag_d6"),
        (date(2025, 11, 9), "lag_d13"),
    ],
)
def test_lag_from_the_25_hour_day_takes_the_first_02_00(fx_store, calendar, target, name):
    """Wall-clock rule: target 02:00 reads the FIRST (CEST) 02:00 of the 25-hour lag day, the repeated hour is
    dropped, every later local hour reads its own stamp."""
    load = fx_store.series("load_actual")
    lag_day = _day(load, date(2025, 10, 26))
    assert len(lag_day) == 25
    expected = np.delete(lag_day, 3)  # index 3 is the second 02:00 (CET)
    f = _lags(fx_store, calendar, target)
    assert len(f) == 24
    assert f[name].to_numpy() == pytest.approx(expected, abs=0)
    assert f[name].iloc[2] == lag_day[2] != lag_day[3]


@pytest.mark.parametrize(
    "name, days_back, lag_day",
    [
        ("lag_d1", 2, date(2025, 10, 24)),
        ("lag_d2", 3, date(2025, 10, 23)),
        ("lag_d6", 7, date(2025, 10, 19)),
        ("lag_d13", 14, date(2025, 10, 12)),
    ],
)
def test_25_hour_target_day_reads_the_same_wall_clock_hour_twice(
    fx_store, calendar, name, days_back, lag_day
):
    """Both 02:00 rows of the 25-hour target day get the lag day's 02:00 (identical features, review M-6)."""
    load = fx_store.series("load_actual")
    assert date(2025, 10, 26) - timedelta(days=days_back) == lag_day
    v = _day(load, lag_day)
    assert len(v) == 24
    f = _lags(fx_store, calendar, date(2025, 10, 26))
    assert len(f) == 25
    assert f[name].to_numpy() == pytest.approx(np.insert(v, 3, v[2]), abs=0)


@pytest.mark.parametrize(
    "target, name",
    [
        (date(2025, 4, 1), "lag_d1"),  # 2 days after the 23-hour day 2025-03-30
        (date(2025, 4, 2), "lag_d2"),
        (date(2025, 4, 6), "lag_d6"),
        (date(2025, 4, 13), "lag_d13"),
    ],
)
def test_lag_from_the_23_hour_day_fills_the_missing_02_00_from_01_00(fx_store, calendar, target, name):
    """Spring rule: the local hour 02:00 does not exist on the lag day, the target's 02:00 takes 01:00."""
    store = _synthetic_store(fx_store, "2025-03-01T00:00:00Z", "2025-04-20T00:00:00Z")
    load = store.series("load_actual")
    lag_day = _day(load, date(2025, 3, 30))
    assert len(lag_day) == 23
    expected = np.insert(lag_day, 2, lag_day[1])
    f = _lags(store, calendar, target)
    assert len(f) == 24
    assert not f[name].isna().any()
    assert f[name].to_numpy() == pytest.approx(expected, abs=0)
    assert f[name].iloc[2] == f[name].iloc[1]


def test_23_hour_target_day_skips_the_missing_hour(fx_store, calendar):
    store = _synthetic_store(fx_store, "2025-03-01T00:00:00Z", "2025-04-20T00:00:00Z")
    load = store.series("load_actual")
    f = _lags(store, calendar, date(2025, 3, 30))
    assert len(f) == 23 and hours_in_day(date(2025, 3, 30)) == 23
    for name, days_back in (("lag_d1", 2), ("lag_d2", 3), ("lag_d6", 7), ("lag_d13", 14)):
        v = _day(load, date(2025, 3, 30) - timedelta(days=days_back))
        assert len(v) == 24
        assert f[name].to_numpy() == pytest.approx(np.delete(v, 2), abs=0), name  # no 02:00 on the target day


def test_present_nan_hour_is_not_forward_filled(fx_store, calendar):
    """The forward fill is only for hours that do not exist; an observed NaN stays NaN."""
    load = fx_store.series("load_actual")
    hole = pd.Timestamp("2025-11-03T09:00:00Z")  # 10:00 local on 11-03
    obs = fx_store.observations.copy()
    obs.loc[(obs["series"] == "load_actual") & (obs["ts_utc"] == hole), "value"] = np.nan
    store = Store(observations=obs, weather=fx_store.weather, region="DE")
    f = _lags(store, calendar, date(2025, 11, 5))
    assert np.isnan(f["lag_d1"].iloc[10])
    assert f["lag_d1"].iloc[9] == load.loc[pd.Timestamp("2025-11-03T08:00:00Z")]
    assert f["lag_d1"].notna().sum() == 23


def test_weather_run_overrun_is_bounded():
    """Run behind the weather value of a target hour = its stamp - 48 h. Against the nominal cut-off (local
    midnight of the issue day) radiation overruns by at most one hour, only on target days for which D or D+1 is
    the 25-hour day, and temperature never overruns (docs/data-notes.md)."""
    offset = pd.Timedelta(days=FeatureSpec.__dataclass_fields__["weather_offset_days"].default)
    assert offset == pd.Timedelta(hours=48) and pd.Timedelta(hours=1) == RADIATION_SHIFT
    overrun_days = []
    for target in daterange(date(2024, 1, 1), date(2026, 12, 31)):
        idx = day_index(target)
        cutoff = cutoff_utc(target - timedelta(days=1))
        temp_over = (idx - offset).max() - cutoff
        ssr_over = (idx + RADIATION_SHIFT - offset).max() - cutoff
        assert temp_over <= pd.Timedelta(0), target
        assert ssr_over <= pd.Timedelta(hours=1), target
        long_day = 25 in (hours_in_day(target), hours_in_day(target - timedelta(days=1)))
        if ssr_over > pd.Timedelta(0):
            overrun_days.append(target)
            assert long_day, target
        if long_day:
            assert ssr_over == pd.Timedelta(hours=1), target
    # Two target days per autumn (the 25-hour day and the day after it).
    assert overrun_days == [
        date(2024, 10, 27),
        date(2024, 10, 28),
        date(2025, 10, 26),
        date(2025, 10, 27),
        date(2026, 10, 25),
        date(2026, 10, 26),
    ]
