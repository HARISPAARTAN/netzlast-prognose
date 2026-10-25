"""Calibration window and exclusion counts (docs/backtest-notes.md)."""

from datetime import date, timedelta

import numpy as np

from lastprog.backtest import BacktestResult, _window, run_backtest
from lastprog.evaluation import exclusion_counts, results_markdown, score_points
from lastprog.timekeys import cutoff_utc, day_index


def _history(first: date, last: date) -> dict:
    out, d = {}, first
    while d <= last:
        idx = day_index(d + timedelta(days=1))
        out[d] = (idx, np.zeros((len(idx), 3)))
        d += timedelta(days=1)
    return out


def test_window_stops_at_target_day_d_minus_1_under_the_midnight_rule():
    origin = date(2025, 11, 10)
    hist = _history(date(2025, 11, 1), origin - timedelta(days=1))
    win = _window(hist, origin, cutoff_utc(origin), 3)
    # newest usable origin is D-2 (target day D-1); D-1 has its outcome after the cut-off
    assert win == [date(2025, 11, 6), date(2025, 11, 7), date(2025, 11, 8)]


def test_window_loses_a_further_origin_under_the_noon_rule():
    origin = date(2025, 11, 10)
    hist = _history(date(2025, 11, 1), origin - timedelta(days=1))
    win = _window(hist, origin, cutoff_utc(origin, "noon_of_previous_day"), 3)
    # cut-off is noon of D-1: the target day D-1 is only half observed, so D-3 is the newest origin
    assert win[-1] == date(2025, 11, 7)


def test_window_never_contains_an_unobserved_target_hour(fx_settings, fx_store):
    last = date(2025, 11, 4)
    for rule in ("local_midnight_of_issue_day", "noon_of_previous_day"):
        result = run_backtest(fx_settings, fx_store, last, last, ["lgbm_cqr"], rule)
        assert result.cutoff_rule == rule
        idx, q = result.outputs["lgbm_cqr"][last]
        assert not np.isnan(q).any() and idx[0] > cutoff_utc(last, rule)


def test_exclusion_counts_report_nan_rows(fx_store):
    taus = np.round(np.arange(1, 20) * 0.05, 2)
    grid = np.linspace(1.0, 3.0, 19)
    day = date(2025, 11, 3)
    idx = day_index(day)
    q = np.tile(grid, (len(idx), 1))
    q[:5] = np.nan  # unadjusted rows
    far = date(2030, 1, 1)  # no observation exists: missing target
    result = BacktestResult(
        taus,
        [day, far],
        {"m": {day: (idx, q), far: (day_index(far), np.tile(grid, (24, 1)))}},
        "local_midnight_of_issue_day",
    )
    counts = exclusion_counts(result, fx_store)["m"]
    assert counts == {"n_rows": 48, "n_excluded": 5 + 24, "n_unadjusted": 5, "n_missing_target": 24}
    points = score_points(result, fx_store)
    assert len(points) == len(idx) - 5  # excluded rows never reach the means


def test_markdown_lists_the_excluded_counts():
    summary = {
        "models": {},
        "excluded": {"lgbm_cqr": {"n_rows": 48, "n_excluded": 5, "n_unadjusted": 5, "n_missing_target": 0}},
    }
    run = {
        "run_id": "x",
        "command": "c",
        "git_sha": "s",
        "store_hash": "h",
        "config_hash": "c" * 16,
        "runtime_s": 1.0,
        "seed": 1,
        "period": ["a", "b"],
        "cutoff_rule": "r",
    }
    assert "| lgbm_cqr | 48 | 5 | 5 | 0 |" in results_markdown(summary, run)
