import math

import numpy as np
import pytest
from scipy.stats import norm

from lastprog.dmtest import dm_statistic, dm_test, newey_west_variance
from lastprog.metrics import crps_grid, crps_normal, interval_bounds, pinball, pit_bin, point_scores, winkler

TAUS = np.round(np.arange(1, 20) * 0.05, 2)


def test_pinball_hand_computed():
    y = np.array([10.0])
    q = np.array([[8.0, 12.0]])
    taus = np.array([0.1, 0.9])
    # tau=0.1, q=8 below y: 0.1 * 2 = 0.2; tau=0.9, q=12 above y: (0.9 - 1) * (10 - 12) = 0.2
    assert pinball(y, q, taus).tolist() == [[pytest.approx(0.2), pytest.approx(0.2)]]
    assert pinball(np.array([5.0]), np.array([[5.0]]), np.array([0.5])).tolist() == [[0.0]]


def test_grid_crps_within_one_percent_of_normal_closed_form():
    rng = np.random.default_rng(20261025)
    ys = rng.standard_normal(20000)
    q = np.tile(norm.ppf(TAUS), (len(ys), 1))
    grid = crps_grid(ys, q, TAUS).mean()
    exact = np.mean([crps_normal(float(y), 0.0, 1.0) for y in ys])
    assert abs(grid / exact - 1) < 0.01
    assert exact == pytest.approx(1 / math.sqrt(math.pi), rel=0.01)


def test_coverage_width_and_winkler():
    y = np.array([1.0, 5.0, -5.0])
    q = np.tile(norm.ppf(TAUS), (3, 1))
    lo, hi = interval_bounds(q, TAUS, 0.8)
    assert lo[0] == pytest.approx(norm.ppf(0.1)) and hi[0] == pytest.approx(norm.ppf(0.9))
    sc = point_scores(y, q, TAUS)
    assert sc["cov_80"].tolist() == [1.0, 0.0, 0.0]
    assert sc["width_80"][0] == pytest.approx(hi[0] - lo[0])
    w = winkler(np.array([5.0]), np.array([-1.0]), np.array([1.0]), 0.8)
    assert w[0] == pytest.approx(2.0 + (2 / 0.2) * 4.0)


def test_pit_rank():
    q = np.tile(TAUS, (3, 1))
    assert pit_bin(np.array([0.0, 0.5, 1.0]), q).tolist() == [0, 9, 19]


def test_dm_statistic_hand_computed():
    d = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # lag 0: variance 2, DM = 3 / sqrt(2/5); HLN factor sqrt((5+1-2)/5) -> 3 * sqrt(2)
    assert newey_west_variance(d, 0) == pytest.approx(2.0)
    assert dm_statistic(d, lag=0) == pytest.approx(3 * math.sqrt(2))
    # lag 1: gamma_1 = 0.8, weight 0.5 -> variance 2.8; 3 / sqrt(0.56) * sqrt(0.8)
    assert newey_west_variance(d, 1) == pytest.approx(2.8)
    assert dm_statistic(d, lag=1) == pytest.approx(3 / math.sqrt(0.56) * math.sqrt(0.8))


def test_dm_test_direction():
    rng = np.random.default_rng(1)
    a = rng.normal(1.0, 0.1, 200)
    b = a + 0.5
    r = dm_test(a, b + rng.normal(0, 0.1, 200), lag=7)
    assert r.mean_diff < 0 and r.p_a_better < 0.001 and r.n == 200


def test_dm_test_drops_missing_origins():
    """A gap in one loss series (e.g. the 24 missing hours of the reference forecast) is tolerated."""
    rng = np.random.default_rng(2)
    a = rng.normal(1.0, 0.1, 100)
    b = a + 0.3 + rng.normal(0, 0.1, 100)
    b[10:13] = np.nan
    r = dm_test(a, b, lag=7)
    assert r.n == 97 and not math.isnan(r.statistic)
    degenerate = dm_test(np.ones(10), np.ones(10))
    assert math.isnan(degenerate.statistic) and degenerate.n == 10
