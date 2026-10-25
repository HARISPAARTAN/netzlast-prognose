"""Baselines and the external reference.

`naive_week` (same local hour one week before the target = feature lag_d6), `naive_day` (same local hour on
D-1 = lag_d1) and `tso_reference` (SMARD filter 411 for the target hours) are point forecasts turned into
quantiles by `residual_quantiles`. `mstl_ets` is statsforecast MSTL (seasons 24 and 168, AutoETS trend) on the
trailing weeks before the cut-off, refit at every origin, with native intervals mapped to quantiles.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import OriginInput


class NaiveLag:
    kind = "point"

    def __init__(self, name: str, feature: str) -> None:
        self.name = name
        self.feature = feature

    def predict(self, inp: OriginInput) -> np.ndarray:
        return inp.features[self.feature].to_numpy("float64")


class TsoReference:
    """The operators' day-ahead load forecast. Uses information the models do not have; reported apart."""

    kind = "point"
    name = "tso_reference"

    def predict(self, inp: OriginInput) -> np.ndarray:
        return inp.store.series("load_tso_forecast").reindex(inp.index).to_numpy("float64")


def residual_quantiles(point: np.ndarray, residuals: np.ndarray, taus: np.ndarray) -> np.ndarray:
    """point + empirical quantiles of past residuals (y - point), pooled over hours; NaN without residuals."""
    r = residuals[~np.isnan(residuals)]
    if r.size == 0:
        return np.full((len(point), len(taus)), np.nan)
    return point[:, None] + np.quantile(r, taus)[None, :]


class MstlEts:
    kind = "quantile"
    name = "mstl_ets"

    def __init__(self, taus: np.ndarray, season_lengths: tuple[int, ...], train_days: int) -> None:
        self.taus = taus
        self.season_lengths = list(season_lengths)
        self.train_days = train_days

    def predict(self, inp: OriginInput) -> np.ndarray:
        from statsforecast.models import MSTL, AutoETS

        load = inp.store.series("load_actual")
        hist = load[load.index < inp.cutoff].dropna()
        if hist.empty:
            return np.full((len(inp.index), len(self.taus)), np.nan)
        last = hist.index[-1]
        start = last - pd.Timedelta(hours=self.train_days * 24 - 1)
        grid = pd.date_range(start, last, freq="h")
        y = hist.reindex(grid).interpolate(limit_direction="both").to_numpy("float64")
        h = int((inp.index[-1] - last) / pd.Timedelta(hours=1))
        levels = sorted({int(round(abs(1 - 2 * t) * 100)) for t in self.taus if round(t, 4) != 0.5})
        model = MSTL(season_length=self.season_lengths, trend_forecaster=AutoETS(model="ZZN"))
        fc = model.forecast(y=y, h=h, level=levels)
        steps = ((inp.index - last) / pd.Timedelta(hours=1)).astype(int) - 1
        cols = []
        for t in self.taus:
            t = round(float(t), 4)
            if t == 0.5:
                cols.append(fc["mean"][steps])
            elif t < 0.5:
                cols.append(fc[f"lo-{int(round((1 - 2 * t) * 100))}"][steps])
            else:
                cols.append(fc[f"hi-{int(round((2 * t - 1) * 100))}"][steps])
        return np.sort(np.column_stack(cols), axis=1)
