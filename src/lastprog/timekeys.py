"""Europe/Berlin local days, issue times and information cut-offs. All daylight-saving handling lives here.

Timestamps are timezone-aware pandas Timestamps in UTC. A local day has 23, 24 or 25 hourly points.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

BERLIN = ZoneInfo("Europe/Berlin")
CUTOFF_RULES = ("local_midnight_of_issue_day", "noon_of_previous_day")


def ms_to_utc(ms: int) -> pd.Timestamp:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC")


def utc_to_ms(ts: pd.Timestamp) -> int:
    return int(ts.value // 1_000_000)


def local_midnight_utc(d: date) -> pd.Timestamp:
    """00:00 Europe/Berlin wall-clock time on local day `d`, as a UTC Timestamp."""
    return pd.Timestamp(datetime(d.year, d.month, d.day, tzinfo=BERLIN)).tz_convert("UTC")


def day_index(d: date) -> pd.DatetimeIndex:
    """Hourly UTC instants of local day `d` (23, 24 or 25 points)."""
    start = local_midnight_utc(d)
    end = local_midnight_utc(d + timedelta(days=1))
    return pd.date_range(start, end, freq="h", inclusive="left", name="ts_utc")


def hours_in_day(d: date) -> int:
    return len(day_index(d))


def local_date(ts: pd.Timestamp) -> date:
    return ts.tz_convert(BERLIN).date()


def local_labels(idx: pd.DatetimeIndex) -> list[str]:
    """ISO 8601 local labels with offset, e.g. 2026-10-25T02:00:00+02:00 then 2026-10-25T02:00:00+01:00."""
    return [ts.isoformat() for ts in idx.tz_convert(BERLIN)]


def utc_labels(idx: pd.DatetimeIndex) -> list[str]:
    return [ts.strftime("%Y-%m-%dT%H:%M:%SZ") for ts in idx.tz_convert("UTC")]


def cutoff_utc(issue_date: date, rule: str = "local_midnight_of_issue_day") -> pd.Timestamp:
    """Information cut-off for a forecast issued on `issue_date`: only observations with ts_utc < cut-off.

    `local_midnight_of_issue_day` (default): 00:00 Europe/Berlin of the issue day.
    `noon_of_previous_day` (sensitivity run): 12:00 Europe/Berlin of the day before.
    """
    if rule == "local_midnight_of_issue_day":
        return local_midnight_utc(issue_date)
    if rule == "noon_of_previous_day":
        prev = issue_date - timedelta(days=1)
        return pd.Timestamp(datetime(prev.year, prev.month, prev.day, 12, tzinfo=BERLIN)).tz_convert("UTC")
    raise ValueError(f"unknown cut-off rule {rule!r}, expected one of {CUTOFF_RULES}")


def issue_time_utc(issue_date: date, time_utc: str = "07:00") -> pd.Timestamp:
    hh, mm = (int(x) for x in time_utc.split(":"))
    return pd.Timestamp(issue_date.year, issue_date.month, issue_date.day, hh, mm, tz="UTC")


def target_day_for(issue_date: date, days_ahead: int = 1) -> date:
    return issue_date + timedelta(days=days_ahead)


def daterange(start: date, end: date) -> list[date]:
    """Inclusive list of calendar dates."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
