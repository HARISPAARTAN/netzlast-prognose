"""Monitoring: population stability index of features and rolling live metrics from the forecast log."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PSI_FEATURES = ["lag_d1", "lag_d6", "d1_mean", "d7_mean"]
PSI_ALERT = 0.2


def psi_reference(values: np.ndarray, bins: int = 10) -> dict:
    """Decile edges and bin shares of the training distribution of one feature (stored in the manifest)."""
    values = values[~np.isnan(values)]
    edges = np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)))
    inner = edges[1:-1]
    probs = np.histogram(values, np.concatenate([[-np.inf], inner, [np.inf]]))[0] / values.size
    return {"edges": [float(e) for e in inner], "probs": [float(p) for p in probs]}


def psi(reference: dict, actual: np.ndarray) -> float:
    """Population stability index of `actual` against a `psi_reference`; empty bins get a 1e-4 floor."""
    actual = actual[~np.isnan(actual)]
    if actual.size == 0:
        return float("nan")
    edges = np.concatenate([[-np.inf], np.array(reference["edges"]), [np.inf]])
    e = np.maximum(np.array(reference["probs"]), 1e-4)
    a = np.maximum(np.histogram(actual, edges)[0] / actual.size, 1e-4)
    return float(np.sum((a - e) * np.log(a / e)))


def read_log(log_dir: Path) -> list[dict]:
    """All forecast-log entries (YYYY/MM/YYYY-MM-DD.json), oldest first."""
    files = sorted(Path(log_dir).glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def rolling_live_metrics(entries: list[dict], model: str = "lgbm_cqr", window: int = 28) -> pd.DataFrame:
    """Per scored target day: crps, cov_80, cov_90 and their trailing `window`-day means."""
    rows = []
    for e in entries:
        scored = e.get("scored")
        if scored and model in scored.get("metrics", {}):
            m = scored["metrics"][model]
            rows.append(
                {"target_date": e["target_date_local"], **{k: m[k] for k in ("crps", "cov_80", "cov_90")}}
            )
    df = pd.DataFrame(rows, columns=["target_date", "crps", "cov_80", "cov_90"])
    for k in ("crps", "cov_80", "cov_90"):
        df[f"{k}_roll"] = df[k].rolling(window, min_periods=1).mean()
    return df
