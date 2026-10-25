"""Live forward period: issue the D+1 forecast once per day and score earlier days once observed.

Log layout (orphan branch `forecast-log`): YYYY/MM/YYYY-MM-DD.json per target day with
{"target_date_local", "run": {...}, "models": {name: /forecast document}, "scored": null | {...}} and
freshness.csv (one line per run: run time, newest load timestamp, lag in hours). The live job runs without
weather and tolerates late SMARD publication up to `max_missing_hours` (missing lags are NaN for LightGBM).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .features import build_features
from .metrics import point_scores
from .monitor import PSI_FEATURES, psi
from .pipeline import git_sha
from .service import DataNotReady, Forecaster
from .timekeys import cutoff_utc, day_index

LIVE_MODELS = ("lgbm_cqr", "naive_week")


def entry_path(log_dir: Path, target_day: date) -> Path:
    return Path(log_dir) / f"{target_day:%Y}" / f"{target_day:%m}" / f"{target_day.isoformat()}.json"


def _drift(fc: Forecaster, issue_day: date) -> dict:
    """PSI of lag features over the last 28 target days against the training distribution in the manifest."""
    days = [issue_day - timedelta(days=k) for k in range(27, -1, -1)]
    frames = [build_features(fc.store, d, cutoff_utc(d - timedelta(days=1)), fc.spec) for d in days]
    recent = pd.concat(frames)
    refs = fc.manifest.get("psi_reference", {})
    return {f: round(psi(refs[f], recent[f].to_numpy("float64")), 4) for f in PSI_FEATURES if f in refs}


def issue(fc: Forecaster, log_dir: Path, now: pd.Timestamp, max_missing_hours: int = 24) -> Path | None:
    """Write the entry for the next local day unless it exists. Returns its path, or None when skipped."""
    issue_day = now.tz_convert("Europe/Berlin").date()
    target = issue_day + timedelta(days=1)
    path = entry_path(log_dir, target)
    if path.exists():
        return None
    last = fc.store.last_observed("load_actual")
    models = {}
    errors = {}
    for m in LIVE_MODELS:
        try:
            models[m] = fc.forecast(target, m, max_missing_hours=max_missing_hours)
        except DataNotReady as exc:
            errors[m] = str(exc)
    if not models:
        raise DataNotReady("; ".join(errors.values()))
    cutoff = cutoff_utc(issue_day)
    entry = {
        "target_date_local": target.isoformat(),
        "run": {
            "run_time_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cutoff_used_utc": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_last_ts_utc": None if last is None else last.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "missing_hours_before_cutoff": None
            if last is None
            else max(0, int((cutoff - last) / pd.Timedelta(hours=1)) - 1),
            "model_version": fc.manifest["version"],
            "git_sha": git_sha(fc.settings.root),
            "psi": _drift(fc, issue_day),
            "errors": errors,
        },
        "models": models,
        "scored": None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry, indent=1) + "\n", encoding="utf-8")
    return path


def score_pending(fc: Forecaster, log_dir: Path, now: pd.Timestamp) -> list[Path]:
    """Add actuals, the reference forecast and per-model metrics to every fully observed, unscored entry."""
    load = fc.store.series("load_actual")
    ref = fc.store.series("load_tso_forecast")
    done = []
    for path in sorted(Path(log_dir).glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry.get("scored"):
            continue
        target = date.fromisoformat(entry["target_date_local"])
        idx = day_index(target)
        y = load.reindex(idx).to_numpy("float64")
        if np.isnan(y).any():
            continue
        metrics = {}
        for name, doc in entry["models"].items():
            q = np.array([p["quantiles"] for p in doc["points"]], dtype="float64")
            sc = point_scores(y, q, np.array(doc["quantile_levels"]))
            metrics[name] = {
                k: round(float(np.mean(sc[k])), 4) for k in ("crps", "abs_err", "cov_50", "cov_80", "cov_90")
            }
            metrics[name]["mae"] = metrics[name].pop("abs_err")
        r = ref.reindex(idx).to_numpy("float64")
        reference = None if np.isnan(r).any() else [round(float(v), 2) for v in r]
        if reference is not None:
            metrics["tso_reference"] = {"mae": round(float(np.mean(np.abs(y - r))), 4)}
        entry["scored"] = {
            "scored_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actual": [round(float(v), 2) for v in y],
            "reference": reference,
            "metrics": metrics,
        }
        path.write_text(json.dumps(entry, indent=1) + "\n", encoding="utf-8")
        done.append(path)
    return done


def append_freshness(log_dir: Path, now: pd.Timestamp, last: pd.Timestamp | None) -> None:
    path = Path(log_dir) / "freshness.csv"
    new = not path.exists()
    lag = "" if last is None else f"{(now - last) / pd.Timedelta(hours=1):.1f}"
    with path.open("a", encoding="utf-8") as fh:
        if new:
            fh.write("run_time_utc,data_last_ts_utc,lag_hours\n")
        last_s = "" if last is None else last.strftime("%Y-%m-%dT%H:%M:%SZ")
        fh.write(f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')},{last_s},{lag}\n")
