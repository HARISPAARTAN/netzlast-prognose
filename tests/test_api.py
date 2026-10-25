"""API in demo mode (fixture period, demo model trained into a temporary directory)."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from lastprog.api import app, get_forecaster
from lastprog.service import Forecaster


@pytest.fixture(scope="module")
def client(fx_settings, fx_store, demo_model_dir):
    fc = Forecaster(replace(fx_settings, mode="demo"), fx_store, demo_model_dir)
    app.dependency_overrides[get_forecaster] = lambda: fc
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["mode"] == "demo" and body["model"] == "lgbm_cqr"
    assert body["model_version"] == "2025.10.0"
    assert body["data_last_ts_utc"] == "2025-11-09T22:00:00Z"


def test_forecast_shape_and_25_points_on_dst_day(client):
    r = client.get("/forecast", params={"target_date": "2025-10-26"})
    assert r.status_code == 200
    body = r.json()
    assert body["region"] == "DE" and body["unit"] == "MWh" and body["timezone"] == "Europe/Berlin"
    assert body["model"]["name"] == "lgbm_cqr" and body["model"]["version"] == "2025.10.0"
    assert body["model"]["trained_until"] == "2025-10-24T22:00:00Z"
    assert body["issue_time_utc"] == "2025-10-25T07:00:00Z"
    assert body["information_cutoff_utc"] == "2025-10-24T22:00:00Z"
    assert len(body["quantile_levels"]) == 19 and body["interval_levels"] == [0.5, 0.8, 0.9]
    assert len(body["points"]) == 25
    p = body["points"][0]
    assert p["ts_utc"] == "2025-10-25T22:00:00Z" and p["ts_local"] == "2025-10-26T00:00:00+02:00"
    assert p["quantiles"] == sorted(p["quantiles"]) and p["median"] == p["quantiles"][9]
    assert set(p["intervals"]) == {"0.5", "0.8", "0.9"}
    assert body["attribution"] == ["Bundesnetzagentur | SMARD.de (CC BY 4.0)"]


def test_24_points_and_naive_week_and_default(client):
    assert len(client.get("/forecast", params={"target_date": "2025-10-27"}).json()["points"]) == 24
    r = client.get("/forecast", params={"target_date": "2025-10-28", "model": "naive_week"})
    assert r.status_code == 200 and r.json()["model"]["name"] == "naive_week"
    default = client.get("/forecast").json()
    assert default["target_date_local"] == "2025-11-11"


def test_deterministic(client):
    a = client.get("/forecast", params={"target_date": "2025-11-05"}).json()
    b = client.get("/forecast", params={"target_date": "2025-11-05"}).json()
    assert a == b


def test_errors(client):
    assert client.get("/forecast", params={"target_date": "2025-13-01"}).status_code == 400
    before_model = client.get("/forecast", params={"target_date": "2025-10-20"})
    assert before_model.status_code == 400
    assert client.get("/forecast", params={"model": "prophet"}).status_code == 404
    r = client.get("/forecast", params={"target_date": "2025-11-12"})
    assert r.status_code == 409 and "2025-11-09T22:00:00Z" in r.json()["detail"]


def test_models_and_no_model(client, fx_settings, fx_store):
    body = client.get("/models").json()
    assert [m["name"] for m in body] == ["lgbm_cqr", "naive_week"]
    empty = Forecaster(replace(fx_settings, mode="demo"), fx_store, None)
    app.dependency_overrides[get_forecaster] = lambda: empty
    try:
        assert TestClient(app).get("/forecast").status_code == 503
        assert TestClient(app).get("/models").status_code == 503
    finally:
        app.dependency_overrides.clear()
