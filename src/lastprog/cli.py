"""Command line: uv run lastprog <command>."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import date
from pathlib import Path

import typer

from .config import load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Netzlast-Prognose")


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LASTPROG_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _settings(period: str | None = None):
    s = load_settings()
    return s.for_fixtures() if period == "fixtures" else s


@app.callback()
def main() -> None:
    """Netzlast-Prognose: probabilistic day-ahead forecasts of German grid load."""


@app.command()
def fetch(
    from_: str = typer.Option(None, "--from", help="First local day (default: history_start)"),
    to: str = typer.Option(None, "--to", help="Last local day (default: now)"),
    weather: bool = typer.Option(
        False, "--weather", help="Also fetch Open-Meteo Previous Runs (backtest only)"
    ),
    raw_dir: Path = typer.Option(
        None, "--raw-dir", help="Only fill this chunk directory (fixtures), no store"
    ),
) -> None:
    """Download SMARD 410/411 (DE, hour) into data/raw and data/store."""
    from .ingest import fetch_smard, fetch_weather
    from .smard import SmardIndexError

    _setup_logging()
    s = _settings()
    start = date.fromisoformat(from_) if from_ else s.data.history_start
    end = date.fromisoformat(to) if to else None
    try:
        calls = fetch_smard(s, start, end, raw_dir)
    except SmardIndexError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"smard: {calls} HTTP calls")
    if weather:
        wx_end = end or s.backtest.test[1]
        calls = fetch_weather(s, s.weather.start, wx_end)
        typer.echo(f"open-meteo: {calls} HTTP calls")


@app.command("repair-store")
def repair_store() -> None:
    """One-off: stamp rows with a missing fetched_at_utc in data/store (idempotent, values unchanged)."""
    from .store import repair_fetched_at

    for name, n in repair_fetched_at(_settings().paths.store).items():
        typer.echo(f"{name}: {n} rows stamped")


@app.command()
def backtest(
    run_id: str = typer.Option(..., "--run-id"),
    period: str = typer.Option("validation", "--period", help="fixtures, validation or test"),
    models: str = typer.Option(None, "--models", help="Comma-separated; default depends on the period"),
    cutoff_rule: str = typer.Option(
        None, "--cutoff-rule", help="local_midnight_of_issue_day or noon_of_previous_day"
    ),
    write_golden: bool = typer.Option(
        False, "--write-golden", help="fixtures only: rewrite golden_metrics.json"
    ),
    allow_unprotocolled: bool = typer.Option(
        False,
        "--allow-unprotocolled",
        help="test period only: run although tag protocol-v1 is missing or not an ancestor of HEAD; "
        "the run is logged and marked protocol_v1=false",
    ),
) -> None:
    """Rolling-origin backtest; writes runs/<run_id>/."""
    from .pipeline import (
        PERIODS,
        PROTOCOL_TAG,
        default_models,
        execute_backtest,
        load_store,
        protocol_tag_status,
    )

    if period not in PERIODS:
        raise typer.BadParameter(f"period must be one of {PERIODS}")
    if write_golden and period != "fixtures":
        raise typer.BadParameter("--write-golden needs --period fixtures")
    s = _settings(period)
    protocol_v1: bool | None = None
    if period == "test":
        _setup_logging()
        ok, reason = protocol_tag_status(s.root)
        if ok:
            protocol_v1 = True
        elif allow_unprotocolled:
            protocol_v1 = False
            logging.getLogger("lastprog").warning(
                "protocol guard overridden (%s): run %s is NOT a protocol run", reason, run_id
            )
            typer.echo(f"warning: {reason}; run {run_id} is marked protocol_v1=false", err=True)
        else:
            typer.echo(
                f"error: refusing to score the test period: {reason}. "
                f"Tag {PROTOCOL_TAG} before the first test run, or pass --allow-unprotocolled.",
                err=True,
            )
            raise typer.Exit(2)
    chosen = models.split(",") if models else default_models(period)
    out = execute_backtest(s, load_store(s), run_id, period, chosen, cutoff_rule, protocol_v1=protocol_v1)
    for name, m in out["summary"]["models"].items():
        typer.echo(f"{name:15s} crps={m['crps']:10.2f} cov80={m['cov_80']:.3f} cov90={m['cov_90']:.3f}")
    typer.echo(f"runtime {out['run']['runtime_s']} s -> {out['run_dir']}")
    if write_golden:
        golden = s.paths.fixtures / "golden_metrics.json"
        text = json.dumps({"models": out["summary"]["models"]}, indent=1, sort_keys=True) + "\n"
        golden.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {golden}")


@app.command("publish-results")
def publish_results(run_id: str = typer.Option(..., "--run-id")) -> None:
    """Copy runs/<run_id>/{summary,run}.json to docs/results/<run_id>/ and write results.md there."""
    from .evaluation import results_markdown

    s = load_settings()
    src, dst = s.paths.runs / run_id, s.paths.results / run_id
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("summary.json", "run.json"):
        shutil.copyfile(src / name, dst / name)
    summary = json.loads((dst / "summary.json").read_text(encoding="utf-8"))
    run = json.loads((dst / "run.json").read_text(encoding="utf-8"))
    (dst / "results.md").write_text(results_markdown(summary, run), encoding="utf-8")
    typer.echo(str(dst))


@app.command()
def tune() -> None:
    """Grid of 12 LightGBM settings on the validation year; writes docs/results/tuning-v1.json."""
    from .pipeline import load_store
    from .tuning import tune as run_tune

    _setup_logging()
    s = _settings()
    out = run_tune(s, load_store(s), s.paths.results / "tuning-v1.json")
    typer.echo(json.dumps(out["best"]))


@app.command()
def train(
    as_of: str = typer.Option(..., "--as-of", help="Issue day of the refit (first day of a month)"),
    period: str = typer.Option(None, "--period", help="'fixtures' trains the demo model"),
    out: Path = typer.Option(None, "--out", help="Output root (default: paths.models)"),
    results: str = typer.Option("test-v1", "--results", help="Run id whose summary goes into the manifest"),
) -> None:
    """Fit the served model at origin --as-of and write <root>/<version>/ plus <root>/LATEST.

    <root> is paths.models, or data/fixtures/model with --period fixtures (the demo model)."""
    from .api import models_root
    from .pipeline import load_store
    from .service import train_model

    s = _settings(period)
    summary_path = s.paths.results / results / "summary.json"
    test_metrics = {}
    if summary_path.exists():
        models = json.loads(summary_path.read_text(encoding="utf-8"))["models"]
        test_metrics = {k: models[k] for k in ("lgbm_cqr", "naive_week") if k in models}
    root = out or models_root(s)
    model_dir = train_model(s, load_store(s), date.fromisoformat(as_of), root, test_metrics)
    (Path(root) / "LATEST").write_text(model_dir.name + "\n", encoding="utf-8")
    typer.echo(str(model_dir))


@app.command()
def forecast(
    target_date: str = typer.Option(None, "--target-date"),
    model: str = typer.Option("lgbm_cqr", "--model"),
    max_missing_hours: int = typer.Option(0, "--max-missing-hours"),
) -> None:
    """Print the /forecast document for one target day."""
    from .api import build_forecaster

    fc = build_forecaster()
    day = date.fromisoformat(target_date) if target_date else fc.default_target()
    typer.echo(json.dumps(fc.forecast(day, model, max_missing_hours), indent=1))


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the API with uvicorn."""
    import uvicorn

    uvicorn.run("lastprog.api:app", host=host, port=port)
