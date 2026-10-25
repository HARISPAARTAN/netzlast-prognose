"""SMARD chunk client (Bundesnetzagentur | SMARD.de, CC BY 4.0).

Adapted from the owner's MIT-licensed energiewende-monitor (src/ewmonitor/smard.py): chunk index, weekly
chunks, atomic cache writes, re-download of chunks cached before they were complete, retry rules and
DST-correct chunk ends are kept; the SQL staging keys are dropped. Rows go to the Parquet store.

Index: {base}/{filter}/{region}/index_{resolution}.json -> {"timestamps": [ms, ...]}
Chunk: {base}/{filter}/{region}/{filter}_{region}_{resolution}_{ms}.json -> {"meta_data": ..., "series": [[ms, v|null]]}
A chunk starts at Monday 00:00 Europe/Berlin and ends at local midnight seven calendar days later, so an hourly
chunk has 168 rows, 167 in the spring daylight-saving week and 169 in the autumn one.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import pandas as pd

from .net import HttpClient, NotFoundError
from .timekeys import BERLIN, local_midnight_utc, ms_to_utc, utc_to_ms

log = logging.getLogger(__name__)

ROW_COLUMNS = ["series", "filter_id", "region", "ts_utc", "value", "chunk_ts_ms"]
PUBLICATION_LAG_MS = 24 * 3600 * 1000


def chunk_name(filter_id: int, region: str, resolution: str, ts_ms: int) -> str:
    return f"{filter_id}_{region}_{resolution}_{ts_ms}.json"


def chunk_end_ms(ts_ms: int) -> int:
    """Exclusive end of the chunk starting at `ts_ms`: local midnight seven calendar days later."""
    start_day = ms_to_utc(ts_ms).tz_convert(BERLIN).date()
    return utc_to_ms(local_midnight_utc(start_day + timedelta(days=7)))


def parse_chunk(payload: dict, series: str, filter_id: int, region: str, chunk_ts_ms: int) -> pd.DataFrame:
    """One chunk payload to rows. Nulls stay NaN (never zero); a non-numeric value raises ValueError."""
    pairs = payload["series"]
    ts = pd.to_datetime([int(p[0]) for p in pairs], unit="ms", utc=True)
    values = pd.to_numeric(pd.Series([p[1] for p in pairs], dtype="object"), errors="raise").astype("float64")
    return pd.DataFrame(
        {
            "series": series,
            "filter_id": int(filter_id),
            "region": region,
            "ts_utc": ts,
            "value": values.to_numpy(),
            "chunk_ts_ms": int(chunk_ts_ms),
        },
        columns=ROW_COLUMNS,
    )


def parse_chunk_file(path: Path, series: str) -> pd.DataFrame:
    """Parse a cached chunk; filter, region and chunk timestamp come from the file name."""
    filter_id, region, _resolution, ts = Path(path).stem.split("_")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_chunk(payload, series, int(filter_id), region, int(ts))


def select_chunks(timestamps: list[int], start_ms: int, end_ms: int) -> list[int]:
    """Chunk starts whose chunk [ts, chunk_end_ms(ts)) overlaps the closed range [start_ms, end_ms]."""
    return [ts for ts in sorted(timestamps) if ts <= end_ms and chunk_end_ms(ts) > start_ms]


class SmardClient:
    def __init__(self, http: HttpClient, base_url: str, cache_dir: Path) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)

    def fetch_index(self, filter_id: int, region: str, resolution: str) -> list[int]:
        url = f"{self.base_url}/{filter_id}/{region}/index_{resolution}.json"
        try:
            payload = self.http.get_json(url)
        except NotFoundError:
            log.warning("index not found (404): %s", url)
            return []
        return [int(ts) for ts in payload["timestamps"]]

    def chunk_path(self, filter_id: int, region: str, resolution: str, ts_ms: int) -> Path:
        return self.cache_dir / chunk_name(filter_id, region, resolution, ts_ms)

    def is_cached(self, filter_id: int, region: str, resolution: str, ts_ms: int) -> bool:
        """True when the cache file exists and was written after the chunk was complete."""
        path = self.chunk_path(filter_id, region, resolution, ts_ms)
        complete_ms = chunk_end_ms(ts_ms) + PUBLICATION_LAG_MS
        return path.exists() and path.stat().st_mtime_ns >= complete_ms * 1_000_000

    def download_chunk(
        self, filter_id: int, region: str, resolution: str, ts_ms: int, force: bool = False
    ) -> Path:
        """Cache file of a chunk, downloading it when missing, stale (cached before complete) or forced.

        The payload goes to a sibling ".part" file that then replaces the cache file (atomic on one volume).
        """
        path = self.chunk_path(filter_id, region, resolution, ts_ms)
        if not force and self.is_cached(filter_id, region, resolution, ts_ms):
            return path
        url = f"{self.base_url}/{filter_id}/{region}/{chunk_name(filter_id, region, resolution, ts_ms)}"
        payload = self.http.get_json(url)
        if not isinstance(payload, dict) or not isinstance(payload.get("series"), list):
            raise ValueError(
                f"{path.name}: unexpected payload from {url}, 'series' is not a list; not cached"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        try:
            part.write_text(json.dumps(payload), encoding="utf-8")
            part.replace(path)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        return path

    def fetch_series(
        self,
        series: str,
        filter_id: int,
        region: str,
        resolution: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DataFrame:
        """Download (or reuse) every chunk overlapping [start, end] and return the parsed rows."""
        index = self.fetch_index(filter_id, region, resolution)
        chosen = select_chunks(index, utc_to_ms(start), utc_to_ms(end))
        log.info("%s: %d chunks for %s .. %s", series, len(chosen), start, end)
        frames = [
            parse_chunk_file(self.download_chunk(filter_id, region, resolution, ts), series) for ts in chosen
        ]
        if not frames:
            return pd.DataFrame(columns=ROW_COLUMNS)
        return pd.concat(frames, ignore_index=True)
