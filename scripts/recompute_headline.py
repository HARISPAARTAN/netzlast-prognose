"""Recompute the headline numbers of a backtest run from its archived per-origin outputs.

Needs only pandas and pyarrow, no lastprog code. Reads `<run-dir>/points.parquet` (one row per model, origin
and target hour with the scores) and `<run-dir>/summary.json`, recomputes the pooled CRPS, MAE, 80 % and
90 % coverage with the protocol's rule (models other than `tso_reference` are pooled on the (origin, hour)
keys that all of them have; `tso_reference` is pooled with `naive_week`), the CRPS change against
`naive_week` and `tso_reference`, and the weather sub-period pair from 2025-01-01, and compares them with
`summary.json`. With `--store-dir` (the window-restricted extract, `observations.parquet`) it also checks
that every observed value `y` in the points equals `load_actual` of the extract at that hour.

  uv run python scripts/recompute_headline.py --run-dir runs/test-v1 [--store-dir extract/]

Exit code 0 when every compared number agrees to 1e-6 (relative), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REFERENCE = "tso_reference"
BASELINE = "naive_week"
WEATHER_START = "2025-01-01"
TOL = 1e-6


def _common(points: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    sub = points[points["model"].isin(models)]
    n = sub.groupby(["origin_date", "target_ts_utc"])["model"].transform("nunique")
    return sub[n == len(models)]


def pooled(points: pd.DataFrame) -> dict[str, dict[str, float]]:
    models = sorted(points["model"].unique())
    core = [m for m in models if m != REFERENCE]
    common = _common(points, core)
    out: dict[str, dict[str, float]] = {}
    for m in models:
        p = _common(points, [REFERENCE, BASELINE]) if m == REFERENCE else common
        p = p[p["model"] == m]
        out[m] = {
            "crps": float(p["crps"].mean()),
            "mae": float(p["abs_err"].mean()),
            "cov_80": float(p["cov_80"].mean()),
            "cov_90": float(p["cov_90"].mean()),
            "n_origins": int(p["origin_date"].nunique()),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--store-dir", help="directory with the window-restricted observations.parquet")
    a = ap.parse_args(argv)

    run = Path(a.run_dir)
    points = pd.read_parquet(run / "points.parquet")
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    mine = pooled(points)
    bad = 0

    print(f"{'model':14s} {'crps':>11s} {'mae':>11s} {'cov_80':>8s} {'cov_90':>8s}  vs summary.json")
    for m, v in mine.items():
        ref = summary["models"][m]
        diffs = {k: abs(v[k] - ref[k]) / max(abs(ref[k]), 1.0) for k in ("crps", "mae", "cov_80", "cov_90")}
        ok = all(d <= TOL for d in diffs.values()) and v["n_origins"] == ref["n_origins"]
        bad += not ok
        print(
            f"{m:14s} {v['crps']:11.4f} {v['mae']:11.4f} {v['cov_80']:8.4f} {v['cov_90']:8.4f}  "
            f"{'ok' if ok else 'MISMATCH ' + str(diffs)}"
        )

    if "lgbm_cqr" in mine:
        h = mine["lgbm_cqr"]["crps"]
        if BASELINE in mine:
            print(f"lgbm_cqr vs {BASELINE}: {100 * (h / mine[BASELINE]['crps'] - 1):+.2f} %")
        if REFERENCE in mine:
            ref_p = _common(points, ["lgbm_cqr", REFERENCE])
            pair = ref_p.groupby("model")["crps"].mean()
            print(
                f"lgbm_cqr vs {REFERENCE} (common points): {100 * (pair['lgbm_cqr'] / pair[REFERENCE] - 1):+.2f} %"
            )
    if {"lgbm_cqr", "lgbm_cqr_wx"} <= set(mine):
        sub = points[points["origin_date"] >= pd.Timestamp(WEATHER_START)]
        sub = _common(sub, ["lgbm_cqr", "lgbm_cqr_wx"])
        wx, no = (sub[sub.model == m]["crps"].mean() for m in ("lgbm_cqr_wx", "lgbm_cqr"))
        n = sub["origin_date"].nunique()
        h3 = summary["hypotheses"]["H3"]
        ok = abs(wx - h3["crps_wx"]) <= TOL * wx and abs(no - h3["crps_no_wx"]) <= TOL * no
        bad += not ok
        print(
            f"weather sub-period from {WEATHER_START}: with {wx:.4f}, without {no:.4f}, "
            f"{n} origins  {'ok' if ok else 'MISMATCH'}"
        )

    if a.store_dir:
        obs = pd.read_parquet(Path(a.store_dir) / "observations.parquet")
        sel = obs[obs["series"] == "load_actual"]
        load = pd.Series(
            sel["value"].to_numpy(), index=pd.DatetimeIndex(pd.to_datetime(sel["ts_utc"], utc=True))
        )
        look = points[["target_ts_utc", "y"]].drop_duplicates()
        stored = look["target_ts_utc"].map(load)
        diff = (stored - look["y"]).abs()
        n_bad = int(((diff > 1e-9) | (stored.isna() != look["y"].isna())).sum())
        bad += n_bad > 0
        print(
            f"observed values y vs extract: {len(look)} hours, {n_bad} differ  {'ok' if not n_bad else 'MISMATCH'}"
        )

    print("all numbers agree" if not bad else f"{bad} check(s) failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
