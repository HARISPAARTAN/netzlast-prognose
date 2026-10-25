"""Shared fixtures. Every test runs offline: LASTPROG_OFFLINE=1 makes any HTTP call raise."""

from __future__ import annotations

import os

os.environ["LASTPROG_OFFLINE"] = "1"
os.environ.pop("LASTPROG_DATA_DIR", None)
os.environ.pop("LASTPROG_MODE", None)

import pytest  # noqa: E402

from lastprog.config import load_settings  # noqa: E402
from lastprog.store import Store  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def fx_settings(settings):
    return settings.for_fixtures()


@pytest.fixture(scope="session")
def fx_store(fx_settings):
    return Store.from_chunk_dir(fx_settings.paths.fixtures / "smard", fx_settings.data.region)


@pytest.fixture(scope="session")
def demo_model_dir(tmp_path_factory, fx_settings, fx_store):
    """The demo model trained into a temporary directory (the repository does not hold model files)."""
    from lastprog.service import train_model

    return train_model(fx_settings, fx_store, fx_settings.demo_as_of, tmp_path_factory.mktemp("models"))
