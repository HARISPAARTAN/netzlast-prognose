"""Full mode: the service follows the store and models/LATEST on disk without a restart (Task 6 review I-4)."""

import json
import shutil
from dataclasses import replace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from lastprog import api
from lastprog.service import Forecaster, ModelIntegrityError


@pytest.fixture()
def disk(tmp_path, monkeypatch, fx_settings, fx_store, demo_model_dir):
    """A full-mode layout under tmp_path: store/observations.parquet cut at 2025-11-06, models/LATEST."""
    store_dir, models = tmp_path / "store", tmp_path / "models"
    store_dir.mkdir()
    shutil.copytree(demo_model_dir, models / "2025.10.0")
    (models / "LATEST").write_text("2025.10.0\n", encoding="utf-8")
    obs = fx_store.observations
    obs[obs["ts_utc"] < pd.Timestamp("2025-11-06T00:00:00Z")].to_parquet(store_dir / "observations.parquet")
    paths = replace(fx_settings.paths, store=store_dir, models=models)
    settings = replace(fx_settings, mode="full", is_fixtures=False, paths=paths)
    monkeypatch.setattr(api, "_settings", lambda: settings)
    monkeypatch.setattr(api, "_current", None)
    api.app.dependency_overrides.clear()
    return {"store": store_dir, "models": models, "obs": obs}


def test_refreshed_store_and_new_latest_are_served_without_a_restart(disk):
    client = TestClient(api.app)
    day = {"target_date": "2025-11-09"}
    r = client.get("/forecast", params=day)
    assert r.status_code == 409 and "2025-11-05T23:00:00Z" in r.json()["detail"]
    assert client.get("/health").json()["data_last_ts_utc"] == "2025-11-05T23:00:00Z"

    disk["obs"].to_parquet(disk["store"] / "observations.parquet")  # the live job refreshed the store
    r = client.get("/forecast", params=day)
    assert r.status_code == 200 and len(r.json()["points"]) == 24
    assert client.get("/health").json()["data_last_ts_utc"] == "2025-11-09T22:00:00Z"

    new = disk["models"] / "2025.11.0"  # a monthly refit landed
    shutil.copytree(disk["models"] / "2025.10.0", new)
    manifest = json.loads((new / "manifest.json").read_text(encoding="utf-8"))
    (new / "manifest.json").write_text(json.dumps({**manifest, "version": "2025.11.0"}), encoding="utf-8")
    assert client.get("/models").json()[0]["version"] == "2025.10.0"
    (disk["models"] / "LATEST").write_text("2025.11.0\n", encoding="utf-8")
    assert client.get("/models").json()[0]["version"] == "2025.11.0"
    assert client.get("/health").json()["model_version"] == "2025.11.0"


def test_unchanged_files_reuse_the_forecaster(disk):
    first = api.get_forecaster()
    assert api.get_forecaster() is first


def test_a_failed_rebuild_keeps_serving_the_previous_state(disk):
    first = api.get_forecaster()
    (disk["store"] / "observations.parquet").write_bytes(b"not a parquet file")
    assert api.get_forecaster() is first


def test_a_corrupted_model_file_is_refused(fx_settings, fx_store, demo_model_dir, tmp_path):
    bad = tmp_path / "bad"
    shutil.copytree(demo_model_dir, bad)
    with (bad / "q_0.50.txt").open("ab") as fh:
        fh.write(b"\n")
    with pytest.raises(ModelIntegrityError, match="q_0.50.txt"):
        Forecaster(fx_settings, fx_store, bad)
