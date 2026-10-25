# Notes for the backtest (carry-over from the Task 3 review)

These points are not enforced by `features.py`, `metrics.py` or `models/conformal.py`; the backtest code has to
honour them and test them.

## Conformal window: only targets observed before the cut-off

The rolling window handed to `cqr_adjust` and `AdaptiveConformal.update` / `adjust` must contain only origins
whose target day has been observed before the information cut-off of the origin being forecast. For the issue day
D (cut-off at local midnight of D, target day D+1) the newest usable window origin is D-2, whose target day is
D-1. The origin D-1 (target day D) is not usable: its outcome is unknown at local midnight of D.

`cqr_adjust` has no access to anything except the arrays it receives, so it cannot enforce this. Task 4 must

- restrict the window to target days up to D-1 (origin up to D-2) when it builds `q_hist` and `y_hist`;
- test it with a sentinel, as `test_no_load_leak_from_observations_at_or_after_cutoff` does for the features:
  replace every outcome at and after the cut-off by a sentinel and assert that the calibrated grid does not change.

## Report missing and unadjusted rows

- `point_scores` returns NaN (never a miss) for a row with a NaN target or a NaN quantile. Aggregate with
  `summarise_scores`, and write `n_rows` and `n_excluded` next to every metric.
- An empty or unusable calibration window gives all-NaN rows in `cqr_adjust` and `AdaptiveConformal.adjust`. Use
  `cqr_adjust_counted` (or `unadjusted_rows`) and report how many rows were left unadjusted, for example at the start
  of the test period and of the weather period.

## Weather run and cut-off

On two target days per autumn (the 25-hour day and the day after it) the run behind the last radiation value is one
hour after the nominal cut-off (see `docs/data-notes.md`). State this figure in `docs/backtest.md` when the leak-free
claim is made.
