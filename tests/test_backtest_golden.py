"""14-origin backtest on ten committed weeks; pooled metrics must match data/fixtures/golden_metrics.json.

Tolerance: relative 1e-9 on Linux (CI, ubuntu-24.04), 1e-6 elsewhere. Regenerate only on purpose, with
`uv run lastprog backtest --period fixtures --run-id golden --write-golden` inside the ubuntu:24.04 container
(scripts/golden-linux.sh), and log the reason in docs/backtest-log.md.
"""

import json
import math
import sys

import pytest

from lastprog.backtest import CORE_MODELS
from lastprog.pipeline import execute_backtest

RTOL = 1e-9 if sys.platform.startswith("linux") else 1e-6


@pytest.fixture(scope="module")
def fixture_run(fx_settings, fx_store, tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    return execute_backtest(
        fx_settings, fx_store, "golden-test", "fixtures", CORE_MODELS, out_root=out, progress=False
    )


def test_fixture_run_shape(fixture_run):
    models = fixture_run["summary"]["models"]
    assert set(models) == set(CORE_MODELS)
    assert models["lgbm_cqr"]["n_origins"] == 14
    assert models["lgbm_cqr"]["n_points"] == 14 * 24 + 1  # includes the 25-hour 2025-10-26
    assert fixture_run["run"]["fits"]["lgbm_qr"] == ["2025-10-17", "2025-11-01"]


def test_matches_golden_file(fixture_run, fx_settings):
    golden = json.loads((fx_settings.paths.fixtures / "golden_metrics.json").read_text(encoding="utf-8"))[
        "models"
    ]
    got = fixture_run["summary"]["models"]
    assert set(got) == set(golden)
    for model, metrics in golden.items():
        for key, expected in metrics.items():
            value = got[model][key]
            assert math.isclose(value, expected, rel_tol=RTOL, abs_tol=1e-12), (
                f"{model}.{key}: {value} != {expected}"
            )


def test_rerun_is_bit_identical(fx_settings, fx_store, fixture_run, tmp_path):
    again = execute_backtest(
        fx_settings, fx_store, "golden-again", "fixtures", CORE_MODELS, out_root=tmp_path, progress=False
    )
    assert again["summary"]["models"] == fixture_run["summary"]["models"]
