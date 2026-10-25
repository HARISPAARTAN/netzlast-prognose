"""Shared fixtures. Every test runs offline: LASTPROG_OFFLINE=1 makes any HTTP call raise."""

from __future__ import annotations

import os

os.environ["LASTPROG_OFFLINE"] = "1"
os.environ.pop("LASTPROG_DATA_DIR", None)
os.environ.pop("LASTPROG_MODE", None)

import pytest  # noqa: E402

from lastprog.config import load_settings  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def fx_settings(settings):
    return settings.for_fixtures()
