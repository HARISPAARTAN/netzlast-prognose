from datetime import date

import pandas as pd
import pytest

from lastprog.timekeys import (
    cutoff_utc,
    day_index,
    hours_in_day,
    issue_time_utc,
    local_labels,
    local_midnight_utc,
    utc_labels,
)


def test_spring_day_has_23_points_with_local_labels():
    idx = day_index(date(2026, 3, 29))
    assert len(idx) == 23
    labels = local_labels(idx)
    assert labels[0] == "2026-03-29T00:00:00+01:00"
    assert labels[1] == "2026-03-29T01:00:00+01:00"
    assert labels[2] == "2026-03-29T03:00:00+02:00"
    assert labels[-1] == "2026-03-29T23:00:00+02:00"
    assert utc_labels(idx)[0] == "2026-03-28T23:00:00Z"


def test_autumn_day_has_25_points_with_repeated_hour():
    idx = day_index(date(2026, 10, 25))
    assert len(idx) == 25
    labels = local_labels(idx)
    assert labels[2] == "2026-10-25T02:00:00+02:00"
    assert labels[3] == "2026-10-25T02:00:00+01:00"
    assert labels[-1] == "2026-10-25T23:00:00+01:00"
    assert utc_labels(idx)[-1] == "2026-10-25T22:00:00Z"


def test_normal_day_and_hours_in_day():
    assert hours_in_day(date(2026, 10, 26)) == 24
    assert hours_in_day(date(2026, 3, 29)) == 23
    assert hours_in_day(date(2025, 10, 26)) == 25


def test_cutoff_is_local_midnight_of_issue_day():
    assert cutoff_utc(date(2026, 10, 25)) == pd.Timestamp("2026-10-24T22:00:00Z")
    assert cutoff_utc(date(2026, 10, 26)) == pd.Timestamp("2026-10-25T23:00:00Z")
    assert local_midnight_utc(date(2026, 3, 29)) == pd.Timestamp("2026-03-28T23:00:00Z")


def test_noon_rule_and_unknown_rule():
    assert cutoff_utc(date(2026, 10, 25), "noon_of_previous_day") == pd.Timestamp("2026-10-24T10:00:00Z")
    with pytest.raises(ValueError, match="cut-off rule"):
        cutoff_utc(date(2026, 10, 25), "issue_time")


def test_issue_time():
    assert issue_time_utc(date(2026, 10, 25), "07:00") == pd.Timestamp("2026-10-25T07:00:00Z")
