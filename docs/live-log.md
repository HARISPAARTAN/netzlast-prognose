# Live log: format and changes

The branch `forecast-log` holds one JSON file per target day (`YYYY/MM/YYYY-MM-DD.json`) and `freshness.csv`.
An entry is written once, before its target day, and gets its `scored` block once the day is fully observed.
Nothing else in an entry changes, with the exceptions listed under "Changes" below.

## Fields of `run`

| Field | Meaning |
|---|---|
| `run_time_utc`, `cutoff_used_utc` | when the forecast was issued and the information cut-off it used |
| `data_last_ts_utc`, `missing_hours_before_cutoff` | newest load value in the store, hours missing in front of the cut-off |
| `model_version`, `git_sha` | served model version and code commit of the run |
| `model_files_digest` | digest of the model files of the build that produced the entry (from 2026-10-26 on; see the refit log) |
| `psi_window_days`, `psi` | population stability index of four lag features over the last `psi_window_days` target days against the training distribution in the manifest; 0.2 is the alert level |
| `errors` | per-model reason when a model could not be issued |

## Changes

- **2026-10-25, PSI window.** The first entry (`2026-10-26.json`) was written with a 28-day window. That window
  alerts permanently, because the load level follows the season and the reference is three years of training data:
  on weekly windows from 2025-01-01 to 2026-10-25, 90 to 100 percent of the 28-day windows were above 0.2 for the
  four features, against 0 percent for a 365-day window. From the next entry on, the window is 365 days
  (`psi_window_days: 365`). The first entry was recomputed with the 365-day window; the original values are kept in
  `run.psi_superseded`. Forecast and scores of the entry are unchanged. An entry without `psi_window_days` used 28
  days and its `psi` is not comparable with 0.2.
- The first entry has no `model_files_digest`; its build is identified by the refit log row of version 2026.10.0.

## Refit log

`models/refit-log.csv` (on `main`) has one row per trained model: version, as-of day, code commit, build time,
platform, Python and LightGBM versions, runner image, Actions run URL, digest of the load data the refit read
(`training_data_sha256`), digest of the model files (`model_files_digest`) and sha256 of the uploaded archive. The
manifest of each model holds the same facts (`built_on`, `training_data`).

- The row of version 2026.10.0 was written afterwards from the Actions run page and `uv.lock`; its manifest predates
  these fields and has no training-data digest.
- A model asset is never replaced. The refit workflow refuses a version that already exists as a release asset; a
  second build in the same month needs a new build number (`2026.10.1`), given as the `build` input of the manual
  run.
