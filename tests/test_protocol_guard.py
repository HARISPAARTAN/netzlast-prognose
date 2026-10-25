"""`lastprog backtest --period test` needs the tag protocol-v1 on an ancestor of HEAD; git SHA carries a dirty flag."""

import json
import subprocess

import pytest
from typer.testing import CliRunner

from lastprog import cli, pipeline
from lastprog.pipeline import git_dirty, git_sha, protocol_tag_status


def _git(path, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_tag_missing(repo):
    ok, reason = protocol_tag_status(repo)
    assert not ok and "does not exist" in reason


def test_tag_on_ancestor_of_head(repo):
    _git(repo, "tag", "-a", "protocol-v1", "-m", "p")
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    assert protocol_tag_status(repo)[0]


def test_tag_on_another_branch_is_refused(repo):
    _git(repo, "checkout", "-q", "-b", "other")
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "other")
    _git(repo, "tag", "-a", "protocol-v1", "-m", "p")
    _git(repo, "checkout", "-q", "-")
    ok, reason = protocol_tag_status(repo)
    assert not ok and "ancestor" in reason


def test_dirty_flag(repo):
    assert git_dirty(repo) is False
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    assert git_dirty(repo) is True
    assert len(git_sha(repo)) == 40


def test_dirty_flag_outside_a_repo(tmp_path):
    assert git_dirty(tmp_path) is None
    assert git_sha(tmp_path) == "unknown"


@pytest.fixture
def fake_run(monkeypatch):
    """Replace the heavy parts of the `backtest` command and record what it was called with."""
    calls = []

    def fake_execute(settings, store, run_id, period, models, cutoff_rule=None, **kw):
        calls.append({"run_id": run_id, "period": period, "kw": kw})
        return {
            "summary": {"models": {}},
            "run": {"runtime_s": 0.0},
            "run_dir": "x",
        }

    monkeypatch.setattr(pipeline, "execute_backtest", fake_execute)
    monkeypatch.setattr(pipeline, "load_store", lambda s: None)
    return calls


def test_cli_refuses_test_period_without_tag(monkeypatch, fake_run):
    monkeypatch.setattr(
        pipeline, "protocol_tag_status", lambda root: (False, "tag protocol-v1 does not exist")
    )
    result = CliRunner().invoke(cli.app, ["backtest", "--run-id", "t", "--period", "test"])
    assert result.exit_code == 2
    assert "protocol-v1" in result.output and "--allow-unprotocolled" in result.output
    assert fake_run == []


def test_cli_override_runs_and_marks_non_protocol(monkeypatch, fake_run, caplog):
    monkeypatch.setattr(
        pipeline, "protocol_tag_status", lambda root: (False, "tag protocol-v1 does not exist")
    )
    with caplog.at_level("WARNING", logger="lastprog"):
        result = CliRunner().invoke(
            cli.app, ["backtest", "--run-id", "t", "--period", "test", "--allow-unprotocolled"]
        )
    assert result.exit_code == 0, result.output
    assert fake_run[0]["kw"]["protocol_v1"] is False
    assert "NOT a protocol run" in caplog.text


def test_cli_with_tag_marks_protocol_run(monkeypatch, fake_run):
    monkeypatch.setattr(pipeline, "protocol_tag_status", lambda root: (True, "tag protocol-v1 at abc"))
    result = CliRunner().invoke(cli.app, ["backtest", "--run-id", "t", "--period", "test"])
    assert result.exit_code == 0, result.output
    assert fake_run[0]["kw"]["protocol_v1"] is True


def test_validation_period_needs_no_tag(monkeypatch, fake_run):
    monkeypatch.setattr(pipeline, "protocol_tag_status", lambda root: (False, "no tag"))
    result = CliRunner().invoke(cli.app, ["backtest", "--run-id", "v", "--period", "validation"])
    assert result.exit_code == 0, result.output
    assert fake_run[0]["kw"]["protocol_v1"] is None


def test_run_json_records_dirty_flag_and_protocol(fx_settings, fx_store, tmp_path):
    out = pipeline.execute_backtest(
        fx_settings,
        fx_store,
        "g",
        "fixtures",
        ["naive_day"],
        out_root=tmp_path,
        progress=False,
        protocol_v1=False,
    )
    run = json.loads((tmp_path / "g" / "run.json").read_text(encoding="utf-8"))
    assert run["git_dirty"] in (True, False, None)
    assert run["protocol_v1"] is False
    from lastprog.evaluation import results_markdown

    assert "Not a protocol run" in results_markdown(out["summary"], out["run"])
