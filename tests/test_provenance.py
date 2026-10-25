"""Refit provenance: build environment, training-data digest, model digest, build suffix and the refit log."""

import csv
import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from lastprog.pipeline import build_environment
from lastprog.service import (
    Forecaster,
    append_refit_log,
    files_digest,
    model_version,
    train_model,
    training_data_digest,
)
from lastprog.store import Store


@pytest.fixture(scope="module")
def manifest(demo_model_dir):
    return json.loads((demo_model_dir / "manifest.json").read_text(encoding="utf-8"))


def test_model_version_carries_a_build_number():
    assert model_version(date(2026, 10, 1)) == "2026.10.0"
    assert model_version(date(2026, 10, 1), 2) == "2026.10.2"


def test_build_environment_names_platform_versions_and_run(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("ImageOS", "ubuntu24")
    monkeypatch.setenv("ImageVersion", "20261013.1")
    env = build_environment()
    assert env["run_url"] == "https://github.com/owner/repo/actions/runs/42"
    assert env["runner_image"] == "ubuntu24 20261013.1"
    assert env["platform"] and env["versions"]["python"] and env["versions"]["lightgbm"]
    monkeypatch.delenv("GITHUB_RUN_ID")
    assert build_environment()["run_url"] is None


def test_manifest_records_provenance(manifest, fx_store):
    built = manifest["built_on"]
    assert built["platform"] and built["versions"]["lightgbm"] and built["built_at_utc"].endswith("Z")
    data = manifest["training_data"]
    assert (
        len(data["sha256"]) == 64
        and data["rows"] > 0
        and data["to_utc_exclusive"] == manifest["trained_until"]
    )
    again = training_data_digest(
        fx_store, pd.Timestamp(data["from_utc"]), pd.Timestamp(data["to_utc_exclusive"])
    )
    assert again == data  # reproducible from the store


def test_training_data_digest_covers_only_the_data_a_refit_reads(fx_store):
    start, cutoff = pd.Timestamp("2025-09-10T00:00:00Z"), pd.Timestamp("2025-10-20T22:00:00Z")
    base = training_data_digest(fx_store, start, cutoff)

    def with_value(ts: str, value: float) -> Store:
        obs = fx_store.observations.copy()
        hit = (obs["series"] == "load_actual") & (obs["ts_utc"] == pd.Timestamp(ts))
        assert hit.sum() == 1
        obs.loc[hit, "value"] = value
        return Store(obs, fx_store.weather)

    # Rows at or after the cut-off, before the start, and other series do not change the digest ...
    assert training_data_digest(with_value("2025-10-20T22:00:00Z", 1.0), start, cutoff) == base
    assert training_data_digest(with_value("2025-09-09T23:00:00Z", 1.0), start, cutoff) == base
    # ... a changed value inside the window does, and so does a missing one.
    assert (
        training_data_digest(with_value("2025-10-01T12:00:00Z", 1.0), start, cutoff)["sha256"]
        != base["sha256"]
    )
    nan = training_data_digest(with_value("2025-10-01T12:00:00Z", np.nan), start, cutoff)
    assert nan["rows_missing"] == 1 and nan["sha256"] != base["sha256"]


def test_files_digest_identifies_the_build(manifest, demo_model_dir, fx_settings, fx_store):
    d = files_digest(manifest)
    assert len(d) == 64
    other = {**manifest, "files_sha256": {**manifest["files_sha256"], "q_0.5.txt": "0" * 64}}
    assert files_digest(other) != d and files_digest({}) is None
    fc = Forecaster(fx_settings, fx_store, demo_model_dir)
    assert fc.health()["model_files_digest"] == d
    assert fc.models()[0]["model_files_digest"] == d and fc.models()[0]["built_on"] == manifest["built_on"]


def test_a_new_build_gets_its_own_version_directory(fx_settings, fx_store, tmp_path):
    out = train_model(fx_settings, fx_store, fx_settings.demo_as_of, tmp_path, build=3)
    assert out.name == f"{fx_settings.demo_as_of.year}.{fx_settings.demo_as_of.month:02d}.3"
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["version"] == out.name


def test_refit_log_appends_once_per_version(demo_model_dir, tmp_path):
    tarball = tmp_path / "model.tar.gz"
    tarball.write_bytes(b"model bytes")
    log = tmp_path / "refit-log.csv"
    row = append_refit_log(log, demo_model_dir / "manifest.json", tarball)
    assert row["tarball_sha256"] == hashlib.sha256(b"model bytes").hexdigest()
    with log.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1 and rows[0]["version"] == "2025.10.0"
    assert rows[0]["training_data_sha256"] and rows[0]["model_files_digest"] and rows[0]["lightgbm"]
    with pytest.raises(ValueError, match="already in"):
        append_refit_log(log, demo_model_dir / "manifest.json", tarball)
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2
