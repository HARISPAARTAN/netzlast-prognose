# Backtest log

Reasons for regenerating `data/fixtures/golden_metrics.json` and other deliberate changes of backtest numbers.

## 2026-10-25: golden file created (Task 4)

- Generated inside `ubuntu:24.04` with `scripts/golden-linux.sh` (Docker Desktop, uv 0.11.8, Python 3.13, `uv sync --locked`), the operating system of CI. The same run on Windows 11 differs by at most 1.2e-15 relative.
- The golden test compares at relative 1e-9 on Linux and 1e-6 elsewhere.
- `lgbm_aci` CRPS is 1754.44, not 1754.51 as in the first draft of the plan: `AdaptiveConformal.update` now skips rows whose forecast grid is NaN (a NaN row is missing, never a hit). The first two warm-up origins have no calibration window, so their NaN grids had counted as perfect hits and pushed alpha up. All other models are unchanged.
- Fixture run exclusions: 337 rows per model, 0 excluded, 0 unadjusted, 0 missing targets (`summary.json` key `excluded`).

## Where the cut-off is enforced

- Features: `build_features(store, target_day, cutoff, spec)` per issue day, cached per target day by `FeatureCache`.
- Training rows: target hours before the origin's cut-off with an observed value.
- Residual and conformal windows: `_window` keeps only earlier origins whose whole target day lies before the cut-off. For issue day D with the midnight rule the newest is D-2 (target day D-1). Under `noon_of_previous_day` the target day D-1 is only half observed, so the newest is D-3.
- Tests: `tests/test_cutoff_leak.py` (sentinel at and after the cut-off, bit-identical forecasts for all models including conformal) and `tests/test_backtest_window.py`.

## Läufe

Jeder Eintrag: Datum (UTC), Lauf, was geschah, warum. Abweichungen vor `protocol-v1` stehen in
`docs/protocol.md`, Abschnitt 12.

| Datum | Lauf | Eintrag |
|---|---|---|
| 2026-10-25 | val-v1 | Baselines und LightGBM auf dem Validierungsjahr bewertet (vor dem Tag), Ausgangswerte der Hyperparameter, Laufzeit 242 s. |
| 2026-10-25 | tuning-v1 | 12 Einstellungen bewertet (Summe der Laufzeiten 1376 s); beste Einstellung 5 (63 Blätter, Lernrate 0,1, 200 Bäume, 100 Mindestproben, Pinball 590,997) eingefroren. |
