import numpy as np
from scipy.stats import norm

from lastprog.models.conformal import AdaptiveConformal, cqr_adjust, pairs, score_quantile

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
