"""Conformalized quantile regression (Romano, Patterson, Candes 2019) on a rolling window of past origins.

For each symmetric pair (tau, 1 - tau) with nominal level 1 - 2 tau the conformity scores
max(q_tau - y, y - q_{1-tau}) of the window are collected; the pair is widened (or narrowed, when the score
quantile is negative) by the ceil((m + 1)(1 - 2 tau)) / m empirical quantile; the median is unchanged; the grid
is re-sorted. Time-series errors are not exchangeable, so the finite-sample guarantee does not hold here;
coverage is judged empirically. Also: a day-part variant and adaptive conformal inference (Gibbs, Candes 2021).
"""

from __future__ import annotations

import math

import numpy as np

DAYPARTS = ((0, 6), (6, 18), (18, 24))  # night, day, evening by local hour


def pairs(taus: np.ndarray) -> list[tuple[int, int, float]]:
    """(lower index, upper index, nominal level) for each symmetric pair, outermost first."""
    k = len(taus)
    return [(i, k - 1 - i, round(float(taus[k - 1 - i] - taus[i]), 4)) for i in range(k // 2)]


def scores(q_hist: np.ndarray, y_hist: np.ndarray, lo: int, hi: int) -> np.ndarray:
    s = np.maximum(q_hist[:, lo] - y_hist, y_hist - q_hist[:, hi])
    return s[~np.isnan(s)]


def score_quantile(s: np.ndarray, level: float) -> float:
    """The ceil((m + 1) level)-th smallest score (the largest when that rank exceeds m); NaN when empty."""
    m = len(s)
    if m == 0:
        return math.nan
    rank = min(m, max(1, math.ceil((m + 1) * level)))
    return float(np.sort(s)[rank - 1])


def daypart_of(hours: np.ndarray) -> np.ndarray:
    out = np.zeros(len(hours), dtype=int)
    for g, (a, b) in enumerate(DAYPARTS):
        out[(hours >= a) & (hours < b)] = g
    return out


def cqr_adjust(
    raw: np.ndarray,
    q_hist: np.ndarray,
    y_hist: np.ndarray,
    taus: np.ndarray,
    groups: np.ndarray | None = None,
    groups_hist: np.ndarray | None = None,
) -> np.ndarray:
    """Calibrated grid for `raw` (n, k) from window forecasts `q_hist` (m, k) and outcomes `y_hist` (m,).

    With `groups` / `groups_hist` (e.g. day parts) each group gets its own score quantile.
    A row whose adjustment cannot be computed (empty window, no usable score, a group without history) is
    returned as an all-NaN row, never as a partly adjusted or raw grid; count them with `unadjusted_rows` or
    use `cqr_adjust_counted`, and report the count with the results.
    """
    if (groups is None) != (groups_hist is None):
        raise ValueError("groups and groups_hist must be given together")
    out = raw.astype("float64").copy()
    if len(q_hist) == 0:
        return np.full_like(out, np.nan)
    if groups is None:
        groups = np.zeros(len(raw), dtype=int)
        groups_hist = np.zeros(len(q_hist), dtype=int)
    for g in np.unique(groups):
        rows, hrows = groups == g, groups_hist == g
        for lo, hi, level in pairs(taus):
            qhat = score_quantile(scores(q_hist[hrows], y_hist[hrows], lo, hi), level)
            if math.isnan(qhat):
                out[rows] = np.nan
                break
            out[rows, lo] = out[rows, lo] - qhat
            out[rows, hi] = out[rows, hi] + qhat
    return np.sort(out, axis=1)


def unadjusted_rows(adjusted: np.ndarray) -> int:
    """Number of rows of a calibrated grid that hold NaN, i.e. rows the calibration could not adjust."""
    return int(np.isnan(adjusted).any(axis=1).sum())


def cqr_adjust_counted(
    raw: np.ndarray,
    q_hist: np.ndarray,
    y_hist: np.ndarray,
    taus: np.ndarray,
    groups: np.ndarray | None = None,
    groups_hist: np.ndarray | None = None,
) -> tuple[np.ndarray, int]:
    """`cqr_adjust` plus the number of rows left unadjusted (all-NaN) for the caller to report."""
    out = cqr_adjust(raw, q_hist, y_hist, taus, groups, groups_hist)
    return out, unadjusted_rows(out)


class AdaptiveConformal:
    """Adaptive conformal inference: per pair, alpha_{t+1} = alpha_t + gamma (alpha_nominal - miss rate).

    The miss rate is that of the newest origin whose target day is observed before the cut-off, scored with
    the intervals this model issued for it. The score quantile is then taken at level 1 - alpha_t.
    """

    def __init__(self, taus: np.ndarray, gamma: float) -> None:
        self.taus = taus
        self.gamma = gamma
        self.alpha = {lo: 1.0 - level for lo, _hi, level in pairs(taus)}

    def update(self, q_prev: np.ndarray, y_prev: np.ndarray) -> None:
        ok = ~np.isnan(y_prev) & ~np.isnan(q_prev).any(axis=1)  # a NaN row is missing, never a hit
        if not ok.any():
            return
        for lo, hi, level in pairs(self.taus):
            miss = float(np.mean((y_prev[ok] < q_prev[ok, lo]) | (y_prev[ok] > q_prev[ok, hi])))
            a = self.alpha[lo] + self.gamma * ((1.0 - level) - miss)
            self.alpha[lo] = min(0.999, max(0.001, a))

    def adjust(self, raw: np.ndarray, q_hist: np.ndarray, y_hist: np.ndarray) -> np.ndarray:
        out = raw.astype("float64").copy()
        for lo, hi, _level in pairs(self.taus):
            qhat = score_quantile(scores(q_hist, y_hist, lo, hi), 1.0 - self.alpha[lo])
            if math.isnan(qhat):  # empty window: all-NaN rows, as in cqr_adjust (count with unadjusted_rows)
                return np.full_like(out, np.nan)
            out[:, lo] -= qhat
            out[:, hi] += qhat
        return np.sort(out, axis=1)
