# Changelog

All notable changes are listed here. Versions follow Semantic Versioning; commits follow Conventional Commits.

## [0.1.0] - 2026-10-25

### Added

- SMARD client (filters 410 and 411, region DE, hourly), Open-Meteo Previous Runs client, Parquet store, fixtures.
- Calendar, population-weighted holiday and lag features with a single information cut-off.
- Baselines (`naive_week`, `naive_day`, `mstl_ets`), LightGBM quantile regression, conformal calibration and two
  ablations (day-part calibration, adaptive conformal inference).
- Rolling-origin backtest with CRPS, pinball, coverage, Winkler, PIT, slices and Diebold-Mariano tests; golden test.
- Pre-registered protocol (`protocol-v1`), tuning on the validation year, results for the test period.
- FastAPI service, Docker image on GHCR, served model 2026.10.0.
- Daily live forecast log on `forecast-log`, monthly refit, static plots page on GitHub Pages.
- Refit provenance: platform, versions, Actions run URL and a digest of the load data read, in the manifest and
  `models/refit-log.csv`; model assets are never replaced, a rebuild takes a new build number.
- German and English READMEs, model card, live-log description, four ADRs, architecture diagram.

### Changed

- PSI drift check compares the last 365 days (not 28) with the training distribution; the first live entry was
  recomputed and keeps its original values.
- The plots page states the caveats on series 411, the `tso_reference` quantiles, the CRPS grid approximation and the
  refit procedure.
