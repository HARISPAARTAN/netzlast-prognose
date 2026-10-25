"""Static page and results markdown from a fixture run plus a one-entry forecast log."""

import json
from dataclasses import replace

import pandas as pd

from lastprog.backtest import CORE_MODELS
from lastprog.evaluation import results_markdown
from lastprog.live import issue, score_pending
from lastprog.pipeline import execute_backtest
from lastprog.report import LIVE_MIN_DAYS, build_site, render_page
from lastprog.service import Forecaster


def test_site_and_markdown(fx_settings, fx_store, demo_model_dir, tmp_path):
    out = execute_backtest(
        fx_settings, fx_store, "fx", "fixtures", CORE_MODELS, out_root=tmp_path / "runs", progress=False
    )
    results = tmp_path / "results" / "fx"
    results.mkdir(parents=True)
    (results / "summary.json").write_text(json.dumps(out["summary"]), encoding="utf-8")
    (results / "run.json").write_text(json.dumps(out["run"]), encoding="utf-8")
    log = tmp_path / "log"
    fc = Forecaster(replace(fx_settings, mode="full"), fx_store, demo_model_dir)
    issue(fc, log, pd.Timestamp("2025-11-03T07:00:00Z"))
    score_pending(fc, log, pd.Timestamp("2025-11-06T07:00:00Z"))
    pages = build_site(tmp_path / "results", "fx", log, tmp_path / "site")
    de, en = (p.read_text(encoding="utf-8") for p in pages)
    assert de.startswith("<!doctype html>") and "<html lang=de>" in de and "<html lang=en>" in en
    for page in (de, en):
        assert (
            page.count("<svg") == 5
        )  # fan, reliability, PIT, by hour, by month; no live chart before 56 days
        assert "(1/56)" in page
        assert "Bundesnetzagentur | SMARD.de" in page
        assert "lgbm_cqr" in page
    assert "Vorläufig" in de and "Preliminary" in en
    md = results_markdown(out["summary"], out["run"])
    assert md.startswith("### Run `fx`") and "| lgbm_cqr |" in md and "Diebold-Mariano" in md


def test_site_without_log_or_results(tmp_path):
    pages = build_site(tmp_path / "none", "missing", None, tmp_path / "site")
    assert all(p.exists() for p in pages)


def test_live_chart_appears_only_after_56_scored_days(fx_settings, fx_store, demo_model_dir, tmp_path):
    fc = Forecaster(replace(fx_settings, mode="full"), fx_store, demo_model_dir)
    path = issue(fc, tmp_path, pd.Timestamp("2025-11-03T07:00:00Z"))
    score_pending(fc, tmp_path, pd.Timestamp("2025-11-06T07:00:00Z"))
    base = json.loads(path.read_text(encoding="utf-8"))
    days = pd.date_range("2025-01-01", periods=LIVE_MIN_DAYS)
    entries = [{**base, "target_date_local": d.date().isoformat()} for d in days]
    few = render_page("en", None, None, entries[: LIVE_MIN_DAYS - 1], False)
    enough = render_page("en", None, None, entries, False)
    assert "Preliminary" in few and f"({LIVE_MIN_DAYS - 1}/{LIVE_MIN_DAYS})" in few
    assert "Preliminary" not in enough and enough.count("<svg") == few.count("<svg") + 1


def _scored_base(fc, tmp_path):
    path = issue(fc, tmp_path, pd.Timestamp("2025-11-03T07:00:00Z"))
    score_pending(fc, tmp_path, pd.Timestamp("2025-11-06T07:00:00Z"))
    return json.loads(path.read_text(encoding="utf-8"))


def test_gate_counts_scored_days_not_entries(fx_settings, fx_store, demo_model_dir, tmp_path):
    fc = Forecaster(replace(fx_settings, mode="full"), fx_store, demo_model_dir)
    base = _scored_base(fc, tmp_path)
    days = pd.date_range("2025-01-01", periods=LIVE_MIN_DAYS)
    scored = [{**base, "target_date_local": d.date().isoformat()} for d in days]
    unscored = {**scored[-1], "scored": None}
    # 55 scored days among 56 entries: the note with the count, no live chart.
    page = render_page("en", None, None, scored[: LIVE_MIN_DAYS - 1] + [unscored], False)
    assert "Preliminary" in page and f"({LIVE_MIN_DAYS - 1}/{LIVE_MIN_DAYS})" in page
    assert page.count("<svg") == 1  # the fan chart only
    # 56 scored days plus further unscored entries: the live chart appears.
    page = render_page("en", None, None, scored + [unscored] * 3, False)
    assert "Preliminary" not in page and page.count("<svg") == 2


def test_page_states_the_backtest_caveats(fx_settings, fx_store, demo_model_dir, tmp_path):
    out = execute_backtest(
        fx_settings, fx_store, "fx", "fixtures", CORE_MODELS, out_root=tmp_path / "runs", progress=False
    )
    de = render_page("de", out["summary"], out["run"], [], False)
    en = render_page("en", out["summary"], out["run"], [], False)
    for page in (de, en):
        assert "411" in page and "tso_reference" in page and "56" in page and "638" in page
        assert "docs/backtest.md" in page and "2/(K+1)" in page
    assert "an einem Stundenwert" in de and "single value" in en
    assert "eigene Konstruktion" in de and "own construction" in en
    assert "19 Quantilen" in de and "19-quantile" in en
    assert "monatlicher Neuschätzung" in de and "monthly refit" in en
