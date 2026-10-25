"""Population stability index and rolling live metrics."""

import json

import numpy as np

from lastprog.monitor import PSI_ALERT, psi, psi_reference, read_log, rolling_live_metrics


def test_psi_is_zero_on_the_reference_and_alerts_on_a_shift():
    rng = np.random.default_rng(1)
    ref_values = rng.normal(50_000, 8_000, 5_000)
    ref = psi_reference(ref_values)
    assert abs(sum(ref["probs"]) - 1) < 1e-12 and len(ref["probs"]) == len(ref["edges"]) + 1
    assert psi(ref, ref_values) < 1e-9
    assert psi(ref, rng.normal(50_000, 8_000, 2_000)) < PSI_ALERT
    assert psi(ref, rng.normal(62_000, 8_000, 2_000)) > PSI_ALERT
    assert np.isnan(psi(ref, np.array([np.nan])))


def test_read_log_and_rolling_metrics(tmp_path):
    for day, crps in (("2026-10-01", 1000.0), ("2026-10-02", 1200.0)):
        d = tmp_path / day[:4] / day[5:7]
        d.mkdir(parents=True, exist_ok=True)
        entry = {
            "target_date_local": day,
            "scored": {"metrics": {"lgbm_cqr": {"crps": crps, "cov_80": 0.8, "cov_90": 0.9}}},
        }
        (d / f"{day}.json").write_text(json.dumps(entry), encoding="utf-8")
    entries = read_log(tmp_path)
    assert [e["target_date_local"] for e in entries] == ["2026-10-01", "2026-10-02"]
    df = rolling_live_metrics(entries + [{"target_date_local": "2026-10-03"}], window=2)
    assert list(df["target_date"]) == ["2026-10-01", "2026-10-02"]
    assert df["crps_roll"].iloc[-1] == 1100.0
    assert rolling_live_metrics([]).empty
