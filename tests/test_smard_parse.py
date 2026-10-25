import json
import os

import numpy as np
import pandas as pd
import pytest
import responses

from lastprog.net import HttpClient, OfflineError
from lastprog.smard import SmardClient, chunk_end_ms, parse_chunk, parse_chunk_file, select_chunks

AUTUMN_CHUNK = 1760911200000  # Monday 2025-10-20 00:00 Europe/Berlin
NEXT_CHUNK = 1761519600000  # Monday 2025-10-27 00:00 Europe/Berlin (after the switch to CET)
SPRING_CHUNK = 1774220400000  # Monday 2026-03-23 00:00 Europe/Berlin
BASE = "https://www.smard.de/app/chart_data"


def test_fixture_chunk_parses_to_169_utc_rows(fx_settings):
    path = fx_settings.paths.fixtures / "smard" / f"410_DE_hour_{AUTUMN_CHUNK}.json"
    df = parse_chunk_file(path, "load_actual")
    assert len(df) == 169
    assert str(df["ts_utc"].dt.tz) == "UTC"
    assert df["ts_utc"].iloc[0] == pd.Timestamp("2025-10-19T22:00:00Z")
    assert df["value"].iloc[0] == 44837.75
    assert (
        set(df["series"]) == {"load_actual"} and set(df["filter_id"]) == {410} and set(df["region"]) == {"DE"}
    )
    assert (df["chunk_ts_ms"] == AUTUMN_CHUNK).all()


def test_nulls_stay_nan_never_zero():
    payload = {"meta_data": {}, "series": [[AUTUMN_CHUNK, 1.5], [AUTUMN_CHUNK + 3_600_000, None]]}
    df = parse_chunk(payload, "load_actual", 410, "DE", AUTUMN_CHUNK)
    assert df["value"].iloc[0] == 1.5
    assert np.isnan(df["value"].iloc[1])


def test_non_numeric_value_raises():
    payload = {"series": [[AUTUMN_CHUNK, "n/a"]]}
    with pytest.raises(ValueError):
        parse_chunk(payload, "load_actual", 410, "DE", AUTUMN_CHUNK)


def test_dst_chunk_ends():
    assert chunk_end_ms(AUTUMN_CHUNK) == NEXT_CHUNK
    assert (chunk_end_ms(AUTUMN_CHUNK) - AUTUMN_CHUNK) // 3_600_000 == 169
    assert (chunk_end_ms(SPRING_CHUNK) - SPRING_CHUNK) // 3_600_000 == 167
    assert select_chunks([AUTUMN_CHUNK, NEXT_CHUNK], NEXT_CHUNK - 1, NEXT_CHUNK - 1) == [AUTUMN_CHUNK]
    assert select_chunks([AUTUMN_CHUNK, NEXT_CHUNK], NEXT_CHUNK, NEXT_CHUNK) == [NEXT_CHUNK]


def test_offline_guard_blocks_http():
    assert os.environ["LASTPROG_OFFLINE"] == "1"
    with pytest.raises(OfflineError):
        HttpClient("test", 0).get_json(f"{BASE}/410/DE/index_hour.json")


@responses.activate
def test_client_downloads_caches_and_refreshes(monkeypatch, tmp_path):
    monkeypatch.delenv("LASTPROG_OFFLINE")
    responses.get(f"{BASE}/410/DE/index_hour.json", json={"timestamps": [AUTUMN_CHUNK]})
    chunk_url = f"{BASE}/410/DE/410_DE_hour_{AUTUMN_CHUNK}.json"
    responses.get(chunk_url, json={"meta_data": {}, "series": [[AUTUMN_CHUNK, 1.0]]})
    client = SmardClient(HttpClient("test", 0), BASE, tmp_path)
    assert client.fetch_index(410, "DE", "hour") == [AUTUMN_CHUNK]
    path = client.download_chunk(410, "DE", "hour", AUTUMN_CHUNK)
    assert json.loads(path.read_text())["series"] == [[AUTUMN_CHUNK, 1.0]]
    assert not path.with_name(path.name + ".part").exists()
    # Written now (after the chunk was complete) -> cached, no second request.
    client.download_chunk(410, "DE", "hour", AUTUMN_CHUNK)
    assert len(responses.calls) == 2
    # A file written before the chunk was complete is fetched again.
    os.utime(path, ns=(AUTUMN_CHUNK * 1_000_000, AUTUMN_CHUNK * 1_000_000))
    client.download_chunk(410, "DE", "hour", AUTUMN_CHUNK)
    assert len(responses.calls) == 3


@responses.activate
def test_missing_index_is_empty_and_bad_payload_not_cached(monkeypatch, tmp_path):
    monkeypatch.delenv("LASTPROG_OFFLINE")
    responses.get(f"{BASE}/999/DE/index_hour.json", status=404)
    responses.get(f"{BASE}/410/DE/410_DE_hour_{AUTUMN_CHUNK}.json", json={"unexpected": True})
    client = SmardClient(HttpClient("test", 0), BASE, tmp_path)
    assert client.fetch_index(999, "DE", "hour") == []
    with pytest.raises(ValueError, match="not cached"):
        client.download_chunk(410, "DE", "hour", AUTUMN_CHUNK)
    assert not any(tmp_path.iterdir())
