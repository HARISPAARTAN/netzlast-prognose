import json

import numpy as np
import pandas as pd
import responses

from lastprog.net import HttpClient
from lastprog.openmeteo import OpenMeteoClient, hourly_name, parse_response

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"


def _payload(fx_settings):
    return json.loads(
        (fx_settings.paths.fixtures / "openmeteo" / "berlin_2024-04-01.json").read_text(encoding="utf-8")
    )


def test_variable_suffix():
    assert hourly_name("temperature_2m", 2) == "temperature_2m_previous_day2"


def test_parse_fixture_response(fx_settings):
    df = parse_response(_payload(fx_settings), "Berlin", ["temperature_2m", "shortwave_radiation"], 2)
    assert set(df["variable"]) == {"temperature_2m", "shortwave_radiation"}
    assert (df["offset_days"] == 2).all()
    assert df["ts_utc"].iloc[0] == pd.Timestamp("2024-04-01T00:00:00Z")
    assert len(df) == 2 * 48
    assert df["value"].notna().all()


def test_nulls_stay_nan():
    payload = {"hourly": {"time": ["2024-01-01T00:00"], "temperature_2m_previous_day2": [None]}}
    df = parse_response(payload, "Berlin", ["temperature_2m"], 2)
    assert np.isnan(df["value"].iloc[0])


@responses.activate
def test_client_caches_response(monkeypatch, tmp_path, fx_settings):
    monkeypatch.delenv("LASTPROG_OFFLINE")
    responses.get(URL, json=_payload(fx_settings))
    from datetime import date

    client = OpenMeteoClient(HttpClient("test", 0), URL, tmp_path)
    args = (
        "Berlin",
        52.52,
        13.40,
        ["temperature_2m", "shortwave_radiation"],
        2,
        date(2024, 4, 1),
        date(2024, 4, 2),
    )
    first = client.fetch_city(*args)
    second = client.fetch_city(*args)
    assert len(responses.calls) == 1
    assert "previous_day2" in responses.calls[0].request.url
    pd.testing.assert_frame_equal(first, second)
