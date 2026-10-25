"""Glue used by the CLI: provenance, loading the store, periods, running and saving a backtest."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
from datetime import date
from importlib import metadata
from pathlib import Path

from .backtest import CORE_MODELS, TEST_MODELS, feature_spec, forecasts_frame, run_backtest
from .config import Settings
from .evaluation import exclusion_counts, per_origin, score_points, summarise
from .store import Store


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def git_sha(root: Path) -> str:
    try:
        out = _git(root, "rev-parse", "HEAD")
    except OSError:
        return "unknown"
    return out.stdout.strip() if out.returncode == 0 else "unknown"


def git_dirty(root: Path) -> bool | None:
    """True when the working tree has uncommitted or untracked (not ignored) changes, None if unknown."""
    try:
        out = _git(root, "status", "--porcelain")
    except OSError:
        return None
    return bool(out.stdout.strip()) if out.returncode == 0 else None


PROTOCOL_TAG = "protocol-v1"


def protocol_tag_status(root: Path, tag: str = PROTOCOL_TAG) -> tuple[bool, str]:
    """(ok, reason): the tag exists and its commit is an ancestor of (or equal to) HEAD."""
    try:
        found = _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}")
        if found.returncode != 0:
            return False, f"tag {tag} does not exist"
        ancestor = _git(root, "merge-base", "--is-ancestor", found.stdout.strip(), "HEAD")
    except OSError as exc:
        return False, f"git is not available ({exc})"
    if ancestor.returncode != 0:
        return False, f"tag {tag} does not point at an ancestor of HEAD"
    return True, f"tag {tag} at {found.stdout.strip()[:10]}"


PERIODS = ("fixtures", "validation", "test")


def load_store(settings: Settings) -> Store:
    """Fixture store for fixture settings, otherwise the Parquet store under paths.store."""
    if settings.is_fixtures:
        return Store.from_chunk_dir(settings.paths.fixtures / "smard", settings.data.region)
    return Store.load(settings.paths.store, settings.data.region)


def period_bounds(settings: Settings, period: str) -> tuple[date, date]:
    b = settings.backtest
    return {"fixtures": b.fixtures, "validation": b.validation, "test": b.test}[period]


def default_models(period: str) -> list[str]:
    return TEST_MODELS if period == "test" else CORE_MODELS


def _versions() -> dict:
    out = {"python": platform.python_version()}
    for pkg in ("lightgbm", "statsforecast", "numpy", "pandas", "holidays", "scipy"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None
    return out


def build_environment() -> dict:
    """Where a model was built: OS, Python and library versions, runner image and Actions run URL (if any)."""
    env = os.environ
    run_url = None
    if env.get("GITHUB_RUN_ID") and env.get("GITHUB_REPOSITORY"):
        server = env.get("GITHUB_SERVER_URL", "https://github.com")
        run_url = f"{server}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "versions": _versions(),
        "runner_image": " ".join(x for x in (env.get("ImageOS"), env.get("ImageVersion")) if x) or None,
        "run_url": run_url,
    }


def execute_backtest(
    settings: Settings,
    store: Store,
    run_id: str,
    period: str,
    models: list[str],
    cutoff_rule: str | None = None,
    out_root: Path | None = None,
    progress: bool = True,
    protocol_v1: bool | None = None,
) -> dict:
    """Run, score and save runs/<run_id>/{forecasts,metrics,points}.parquet, summary.json and run.json."""
    first, last = period_bounds(settings, period)
    result = run_backtest(settings, store, first, last, models, cutoff_rule, progress=progress)
    points = score_points(result, store)
    summary = summarise(
        points,
        result.taus,
        feature_spec(settings, False).calendar,
        settings.backtest.dm_lag,
        headline=settings.model.headline,
        weather_start=settings.backtest.weather_test_start if period == "test" else None,
    )
    summary["excluded"] = exclusion_counts(result, store)
    run_dir = Path(out_root or settings.paths.runs) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    forecasts_frame(result, settings).to_parquet(run_dir / "forecasts.parquet", index=False)
    per_origin(points).to_parquet(run_dir / "metrics.parquet", index=False)
    points.to_parquet(run_dir / "points.parquet", index=False)
    config_bytes = (settings.root / "config.toml").read_bytes()
    run = {
        "run_id": run_id,
        "command": "lastprog " + " ".join(shlex.quote(a) for a in sys.argv[1:]),
        "period": [first.isoformat(), last.isoformat()],
        "models": models,
        "cutoff_rule": result.cutoff_rule,
        "git_sha": git_sha(settings.root),
        "git_dirty": git_dirty(settings.root),
        "protocol_v1": protocol_v1,
        "config_hash": hashlib.sha256(config_bytes).hexdigest(),
        "store_hash": store.snapshot(),
        "seed": settings.model.seed,
        "num_threads": settings.model.num_threads,
        "lgbm": settings.model.lgbm.__dict__,
        "fits": result.fits,
        "runtime_s": round(result.runtime_s, 1),
        "versions": _versions(),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps(run, indent=1) + "\n", encoding="utf-8")
    return {"summary": summary, "run": run, "run_dir": str(run_dir)}
