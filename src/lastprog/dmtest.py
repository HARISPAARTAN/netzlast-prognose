"""Diebold-Mariano test with the Harvey-Leybourne-Newbold correction and Newey-West variance.

d_t = loss_A(t) - loss_B(t) per origin (daily CRPS). Negative mean d favours model A.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class DMResult:
    n: int
    mean_diff: float
    statistic: float
    p_two_sided: float
    p_a_better: float

    def as_dict(self) -> dict:
        return asdict(self)


def newey_west_variance(d: np.ndarray, lag: int) -> float:
    """Long-run variance of d with Bartlett weights 1 - k/(lag+1), k = 1..lag."""
    n = len(d)
    dc = d - d.mean()
    var = float(dc @ dc) / n
    for k in range(1, lag + 1):
        var += 2.0 * (1.0 - k / (lag + 1)) * float(dc[k:] @ dc[:-k]) / n
    return var


def dm_statistic(d: np.ndarray, lag: int, h: int = 1) -> float:
    """HLN-corrected DM statistic: mean(d) / sqrt(NW variance / n) * sqrt((n + 1 - 2h + h(h-1)/n) / n)."""
    d = np.asarray(d, dtype="float64")
    d = d[~np.isnan(d)]
    n = len(d)
    var = newey_west_variance(d, lag)
    if var <= 0:
        return math.nan
    dm = d.mean() / math.sqrt(var / n)
    return dm * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)


def dm_test(loss_a: np.ndarray, loss_b: np.ndarray, lag: int = 7, h: int = 1) -> DMResult:
    """Two-sided and one-sided (A better) p-values from Student t with n-1 degrees of freedom."""
    from scipy import stats

    d = np.asarray(loss_a, dtype="float64") - np.asarray(loss_b, dtype="float64")
    d = d[~np.isnan(d)]
    n = len(d)
    stat = dm_statistic(d, lag, h)
    if math.isnan(stat):
        return DMResult(n, float(d.mean()) if n else math.nan, math.nan, math.nan, math.nan)
    return DMResult(
        n=n,
        mean_diff=float(d.mean()),
        statistic=float(stat),
        p_two_sided=float(2 * stats.t.sf(abs(stat), n - 1)),
        p_a_better=float(stats.t.cdf(stat, n - 1)),
    )
