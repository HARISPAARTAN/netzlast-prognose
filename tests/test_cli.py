import json

import pandas as pd
import pytest
import responses
from typer.testing import CliRunner

from lastprog.cli import app
from lastprog.net import HttpClient
from lastprog.smard import SmardClient, SmardIndexError

BASE = "https://www.smard.de/app/chart_data"
INDEX_URL = f"{BASE}/410/DE/index_hour.json"


@pytest.fixture
def online(monkeypatch, tmp_path):
    monkeypatch.delenv("LASTPROG_OFFLINE")
    monkeypatch.setenv("LASTPROG_DATA_DIR", str(tmp_path))


@pytest.mark.parametrize(
    "kwargs", [{"status": 404}, {"json": {"timestamps": []}}], ids=["404", "empty-index"]
)
@responses.activate
def test_client_raises_on_missing_or_empty_index(online, tmp_path, kwargs):
    responses.get(INDEX_URL, **kwargs)
    client = SmardClient(HttpClient("test", 0), BASE, tmp_path)
    with pytest.raises(SmardIndexError, match="missing .*or empty"):
        client.fetch_series("load_actual", 410, "DE", "hour", *_range())


@pytest.mark.parametrize(
    "kwargs", [{"status": 404}, {"json": {"timestamps": []}}], ids=["404", "empty-index"]
)
@responses.activate
def test_fetch_exits_non_zero_without_writing(online, tmp_path, kwargs):
    responses.get(INDEX_URL, **kwargs)
    result = CliRunner().invoke(app, ["fetch", "--from", "2025-10-01", "--to", "2025-10-07"])
    assert result.exit_code == 1
    assert "index" in result.output and "HTTP calls" not in result.output
    assert not (tmp_path / "store" / "observations.parquet").exists()


def _range():
    return pd.Timestamp("2025-10-01T00:00:00Z"), pd.Timestamp("2025-10-07T00:00:00Z")


def test_train_fixtures_writes_model_and_latest_and_forecast_reads_it(tmp_path, monkeypatch):
    monkeypatch.setenv("LASTPROG_MODE", "demo")
    res = CliRunner().invoke(
        app, ["train", "--period", "fixtures", "--as-of", "2025-10-25", "--out", str(tmp_path)]
    )
    assert res.exit_code == 0, res.output
    assert (tmp_path / "LATEST").read_text(encoding="utf-8").strip() == "2025.10.0"
    manifest = json.loads((tmp_path / "2025.10.0" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "2025.10.0" and set(manifest["psi_reference"]) == {
        "lag_d1",
        "lag_d6",
        "d1_mean",
        "d7_mean",
    }
    assert len(list((tmp_path / "2025.10.0").glob("q_*.txt"))) == 19
