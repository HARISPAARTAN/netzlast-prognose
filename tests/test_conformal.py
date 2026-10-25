import numpy as np
import pytest
from scipy.stats import norm

from lastprog.models.conformal import (
    AdaptiveConformal,
    cqr_adjust,
    cqr_adjust_counted,
    pairs,
    score_quantile,
    unadjusted_rows,
)

TAUS = np.round(np.arange(1, 20) * 0.05, 2)


def _coverage(q, y, level):
    lo = list(TAUS).index(round((1 - level) / 2, 2))
    hi = list(TAUS).index(round(1 - (1 - level) / 2, 2))
    return float(np.mean((y >= q[:, lo]) & (y <= q[:, hi])))


def _base_grid(n, scale):
    return np.tile(norm.ppf(TAUS) * scale, (n, 1))


def test_pairs_and_score_quantile():
    p = pairs(TAUS)
    assert p[0] == (0, 18, 0.9) and p[-1] == (8, 10, 0.1) and len(p) == 9
    assert score_quantile(np.arange(1.0, 11.0), 0.9) == 10.0  # ceil(11 * 0.9) = 10th smallest
    assert np.isnan(score_quantile(np.array([]), 0.9))


def test_iid_coverage_within_three_points_and_widening():
    rng = np.random.default_rng(20261025)
    y_cal, y_test = rng.standard_normal(1344), rng.standard_normal(5000)
    narrow_cal, narrow_test = _base_grid(len(y_cal), 0.5), _base_grid(len(y_test), 0.5)
    out = cqr_adjust(narrow_test, narrow_cal, y_cal, TAUS)
    for level in (0.5, 0.8, 0.9):
        assert abs(_coverage(out, y_test, level) - level) <= 0.03
        assert _coverage(narrow_test, y_test, level) < level - 0.05  # base model was too narrow
    assert np.all(out[:, 0] < narrow_test[:, 0])  # widened


def test_narrowing_when_too_wide_and_monotone_output():
    rng = np.random.default_rng(7)
    y_cal, y_test = rng.standard_normal(1344), rng.standard_normal(5000)
    wide_cal, wide_test = _base_grid(len(y_cal), 3.0), _base_grid(len(y_test), 3.0)
    out = cqr_adjust(wide_test, wide_cal, y_cal, TAUS)
    assert np.all(out[:, 0] > wide_test[:, 0])  # narrowed
    assert abs(_coverage(out, y_test, 0.8) - 0.8) <= 0.03
    assert np.all(np.diff(out, axis=1) >= 0)
    assert np.allclose(out[:, 9], wide_test[:, 9])  # median unchanged


def test_empty_window_gives_nan():
    out = cqr_adjust(_base_grid(3, 1.0), np.empty((0, 19)), np.empty(0), TAUS)
    assert np.isnan(out).all()


def test_aci_moves_alpha_towards_nominal():
    aci = AdaptiveConformal(TAUS, gamma=0.05)
    q = _base_grid(24, 0.1)
    y = np.full(24, 5.0)  # every point missed
    before = aci.alpha[0]
    aci.update(q, y)
    assert aci.alpha[0] < before  # misses -> smaller alpha -> wider intervals


# Empty or unusable windows give explicit NaN rows and a count (Task 3 fix report, review I-2).


def test_empty_window_is_all_nan_and_counted():
    raw = _base_grid(3, 1.0)
    out, n = cqr_adjust_counted(raw, np.empty((0, 19)), np.empty(0), TAUS)
    assert np.isnan(out).all() and n == 3 and unadjusted_rows(out) == 3
    ok, n_ok = cqr_adjust_counted(
        raw, _base_grid(50, 0.5), np.random.default_rng(3).standard_normal(50), TAUS
    )
    assert not np.isnan(ok).any() and n_ok == 0


def test_all_nan_outcomes_give_all_nan_rows_including_the_median():
    out, n = cqr_adjust_counted(_base_grid(2, 1.0), _base_grid(10, 1.0), np.full(10, np.nan), TAUS)
    assert np.isnan(out).all() and n == 2


def test_group_without_history_is_all_nan_for_that_group_only():
    rng = np.random.default_rng(5)
    raw, hist, y = _base_grid(4, 1.0), _base_grid(30, 1.0), rng.standard_normal(30)
    out, n = cqr_adjust_counted(raw, hist, y, TAUS, np.array([0, 0, 1, 1]), np.zeros(30, dtype=int))
    assert n == 2 and np.isnan(out[2:]).all() and not np.isnan(out[:2]).any()


def test_groups_need_groups_hist():
    with pytest.raises(ValueError, match="together"):
        cqr_adjust(_base_grid(2, 1.0), _base_grid(5, 1.0), np.zeros(5), TAUS, np.array([0, 1]), None)


def test_aci_adjust_on_empty_window_is_all_nan():
    aci = AdaptiveConformal(TAUS, gamma=0.05)
    out = aci.adjust(_base_grid(2, 1.0), np.empty((0, 19)), np.empty(0))
    assert np.isnan(out).all() and unadjusted_rows(out) == 2


def test_aci_update_ignores_rows_with_nan_forecasts():
    """A NaN forecast row is missing, never a hit: it must not move alpha."""
    aci = AdaptiveConformal(TAUS, gamma=0.05)
    before = dict(aci.alpha)
    aci.update(np.full((24, 19), np.nan), np.full(24, 5.0))
    assert aci.alpha == before
    q = _base_grid(24, 0.1)
    q[:12] = np.nan  # half the rows unusable, the other half all missed
    aci.update(q, np.full(24, 5.0))
    assert aci.alpha[0] < before[0]
