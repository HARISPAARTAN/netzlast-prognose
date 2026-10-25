"""Hyperparameter tuning of lgbm_qr on the validation year only (at most 12 settings, mean pinball loss)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .backtest import run_backtest
from .config import Settings
from .evaluation import score_points
from .pipeline import git_dirty, git_sha
from .store import Store

TUNING_GRID: list[dict] = [
    {"num_leaves": nl, "learning_rate": lr, "n_estimators": ne, "min_child_samples": mc}
    for nl, mc in ((15, 50), (31, 50), (63, 100))
    for lr, ne in ((0.05, 400), (0.1, 200))
] + [
    {"num_leaves": 31, "learning_rate": 0.03, "n_estimators": 700, "min_child_samples": 50},
    {"num_leaves": 31, "learning_rate": 0.05, "n_estimators": 400, "min_child_samples": 20},
    {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 600, "min_child_samples": 50},
    {"num_leaves": 127, "learning_rate": 0.05, "n_estimators": 400, "min_child_samples": 100},
    {"num_leaves": 15, "learning_rate": 0.1, "n_estimators": 600, "min_child_samples": 20},
    {"num_leaves": 31, "learning_rate": 0.1, "n_estimators": 400, "min_child_samples": 50},
]


def tune(settings: Settings, store: Store, out_path: Path) -> dict:
    """Score lgbm_qr on the validation year for each of the 12 grid settings by mean pinball loss."""
    first, last = settings.backtest.validation
    rows = []
    for i, overrides in enumerate(TUNING_GRID):
        params = replace(settings.model.lgbm, **overrides)
        s = replace(settings, model=replace(settings.model, lgbm=params))
        result = run_backtest(s, store, first, last, ["lgbm_qr"])
        points = score_points(result, store)
        rows.append(
            {
                "setting": i,
                **overrides,
                "pinball": float(points["pinball"].mean()),
                "runtime_s": round(result.runtime_s, 1),
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    best = min(rows, key=lambda r: r["pinball"])
    out = {
        "period": [first.isoformat(), last.isoformat()],
        "grid": rows,
        "best": best,
        "git_sha": git_sha(settings.root),
        "git_dirty": git_dirty(settings.root),
        "store_hash": store.snapshot(),
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out
