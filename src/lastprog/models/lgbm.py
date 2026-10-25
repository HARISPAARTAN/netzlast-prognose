"""LightGBM quantile regression: one global model per quantile (objective "quantile"), rearranged grid.

Deterministic: fixed seed, deterministic=True, force_row_wise=True, fixed num_threads. Models are saved as
LightGBM text files q_0.05.txt ... q_0.95.txt.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..config import LgbmParams


def booster_params(tau: float, params: LgbmParams, seed: int, num_threads: int) -> dict:
    return {
        "objective": "quantile",
        "alpha": float(tau),
        "learning_rate": params.learning_rate,
        "num_leaves": params.num_leaves,
        "min_data_in_leaf": params.min_child_samples,
        "feature_fraction": params.feature_fraction,
        "lambda_l2": params.lambda_l2,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": num_threads,
        "verbosity": -1,
    }


def quantile_file(tau: float) -> str:
    return f"q_{tau:.2f}.txt"


class LgbmQuantile:
    kind = "quantile"

    def __init__(
        self, name: str, taus: np.ndarray, params: LgbmParams, seed: int, num_threads: int, columns: list[str]
    ) -> None:
        self.name = name
        self.taus = taus
        self.params = params
        self.seed = seed
        self.num_threads = num_threads
        self.columns = list(columns)
        self.boosters: list[lgb.Booster] = []
        self.fitted_at = None  # origin date of the last fit

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None:
        data = X[self.columns].to_numpy("float64")
        self.boosters = []
        for tau in self.taus:
            ds = lgb.Dataset(data, label=y, feature_name=self.columns, free_raw_data=False)
            self.boosters.append(
                lgb.train(
                    booster_params(tau, self.params, self.seed, self.num_threads),
                    ds,
                    num_boost_round=self.params.n_estimators,
                )
            )

    def predict_frame(self, X: pd.DataFrame) -> np.ndarray:
        if not self.boosters:
            raise RuntimeError(f"{self.name}: predict before fit")
        data = X[self.columns].to_numpy("float64")
        raw = np.column_stack([b.predict(data, num_threads=self.num_threads) for b in self.boosters])
        return np.sort(raw, axis=1)  # rearrangement (Chernozhukov, Fernandez-Val, Galichon 2010)

    def predict(self, inp) -> np.ndarray:
        return self.predict_frame(inp.features)

    def save(self, out_dir: Path) -> list[str]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        names = []
        for tau, booster in zip(self.taus, self.boosters, strict=True):
            booster.save_model(str(out_dir / quantile_file(tau)))
            names.append(quantile_file(tau))
        return names

    def load(self, model_dir: Path) -> None:
        self.boosters = [lgb.Booster(model_file=str(Path(model_dir) / quantile_file(t))) for t in self.taus]
