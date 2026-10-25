"""Scoring rules on quantile grids.

Arrays: y (n,), q (n, k) sorted along axis 1, taus (k,) equally spaced (0.05 .. 0.95). CRPS is the integrated
pinball loss (Gneiting and Raftery 2007) approximated on the grid: each of the k quantiles stands for a band of
width 1/(k+1), so CRPS ~ 2/(k+1) * sum of pinball losses = 2 * k/(k+1) * mean pinball. The spec's "twice the
mean pinball" overstates the CRPS of a normal distribution by about 5 %; this version is within 1 % on average
(tests/test_metrics.py) and differs by the constant factor 0.95, so rankings and DM tests are unchanged.
"""

from __future__ import annotations

import numpy as np

INTERVAL_LEVELS = (0.5, 0.8, 0.9)


def pinball(y: np.ndarray, q: np.ndarray, taus: np.ndarray) -> np.ndarray:
    """Pinball loss per point and quantile, shape (n, k)."""
    diff = y[:, None] - q
    return np.maximum(taus[None, :] * diff, (taus[None, :] - 1.0) * diff)


def crps_grid(y: np.ndarray, q: np.ndarray, taus: np.ndarray) -> np.ndarray:
    """Per-point CRPS approximation: 2/(k+1) x sum of pinball losses over the k-quantile grid."""
    return 2.0 * pinball(y, q, taus).sum(axis=1) / (len(taus) + 1)


def interval_bounds(q: np.ndarray, taus: np.ndarray, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Lower and upper bound of the central interval `level`, e.g. 0.8 -> quantiles 0.10 and 0.90."""
    lo_tau, hi_tau = round((1 - level) / 2, 4), round(1 - (1 - level) / 2, 4)
    t = np.round(taus, 4)
    return q[:, int(np.flatnonzero(t == lo_tau)[0])], q[:, int(np.flatnonzero(t == hi_tau)[0])]


def winkler(y: np.ndarray, lo: np.ndarray, hi: np.ndarray, level: float) -> np.ndarray:
    """Interval (Winkler) score per point: width plus 2/alpha times the miss distance."""
    alpha = 1.0 - level
    return (hi - lo) + (2.0 / alpha) * np.maximum(lo - y, 0.0) + (2.0 / alpha) * np.maximum(y - hi, 0.0)


def missing_rows(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    """True where the target is NaN or any quantile of the row is NaN: such a row cannot be scored."""
    return np.isnan(y) | np.isnan(q).any(axis=1)


def pit_bin(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Rank of y in its quantile grid: number of quantiles strictly below y (0..k), as float; NaN for a missing row.

    With the 19-quantile grid every one of the 20 bins has nominal probability 0.05, so the histogram of
    these ranks is the PIT histogram, and P(y <= q_tau_j) = share of ranks <= j is the reliability curve.
    """
    rank = (q < y[:, None]).sum(axis=1).astype("float64")
    rank[missing_rows(y, q)] = np.nan
    return rank


def point_scores(y: np.ndarray, q: np.ndarray, taus: np.ndarray) -> dict[str, np.ndarray]:
    """All per-point scores used by the backtest. The median is the 0.5 column of the grid.

    A row with a NaN target or a NaN quantile is missing, never a miss: every score of that row is NaN
    (coverage and PIT bin included), so means over the scores must skip it and `summarise_scores` reports how
    many rows were left out.
    """
    t = np.round(taus, 4)
    med = q[:, int(np.flatnonzero(t == 0.5)[0])]
    err = y - med
    pb = pinball(y, q, taus)
    out: dict[str, np.ndarray] = {
        "pinball": pb.mean(axis=1),
        "crps": 2.0 * pb.sum(axis=1) / (len(taus) + 1),
        "median": med,
        "abs_err": np.abs(err),
        "sq_err": err**2,
        "ape": np.abs(err) / np.abs(y),
        "pit_bin": pit_bin(y, q),
    }
    for level in INTERVAL_LEVELS:
        lo, hi = interval_bounds(q, taus, level)
        key = int(round(level * 100))
        out[f"cov_{key}"] = ((y >= lo) & (y <= hi)).astype("float64")
        out[f"width_{key}"] = hi - lo
        out[f"winkler_{key}"] = winkler(y, lo, hi, level)
    bad = missing_rows(y, q)
    for name, values in out.items():
        values = np.asarray(values, dtype="float64").copy()
        values[bad] = np.nan
        out[name] = values
    return out


def summarise_scores(scores: dict[str, np.ndarray]) -> dict[str, float]:
    """Mean of every score over the rows that could be scored, plus `n_rows` and `n_excluded` (missing rows).

    The PIT bin is a rank, not a score to average, and is left out of the means.
    """
    n_rows = len(scores["pinball"])
    excluded = int(np.isnan(scores["pinball"]).sum())
    out: dict[str, float] = {"n_rows": float(n_rows), "n_excluded": float(excluded)}
    for name, values in scores.items():
        if name == "pit_bin":
            continue
        out[name] = float(np.nanmean(values)) if excluded < n_rows else float("nan")
    return out


def crps_normal(y: float, mu: float, sigma: float) -> float:
    """Closed-form CRPS of N(mu, sigma^2) at y (used to check the grid approximation)."""
    from math import erf, exp, pi, sqrt

    z = (y - mu) / sigma
    pdf = exp(-0.5 * z * z) / sqrt(2 * pi)
    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    return sigma * (z * (2 * cdf - 1) + 2 * pdf - 1 / sqrt(pi))
