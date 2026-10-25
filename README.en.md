# Netzlast-Prognose (German grid load forecast)

[![CI](https://github.com/HARISPAARTAN/netzlast-prognose/actions/workflows/ci.yml/badge.svg)](https://github.com/HARISPAARTAN/netzlast-prognose/actions/workflows/ci.yml)

Calibrated probabilistic forecasts of German grid load for the next day, with a pre-registered backtest, a FastAPI
service in Docker and a daily live log.

Deutsche Fassung: [README.md](README.md)

![Architecture](docs/architecture.svg)

## Summary

**CRPS 42 percent below the seasonal-naive baseline on 730 pre-registered test days (19-quantile grid
approximation); 80 and 90 percent intervals cover 80.1 and 89.8 percent.**

- Every morning at 07:00 UTC: 19 quantiles of hourly grid load (SMARD, region DE) for the next local day.
- Headline model `lgbm_cqr`: LightGBM quantile regression with conformal calibration. Seasonal-naive baseline
  (`naive_week`): the same hour one week earlier.
- Evaluated on two test years (2024-10-01 to 2026-09-30) under a protocol frozen as the git tag `protocol-v1`
  before the test period was scored. Small pre-tag smoke tests are disclosed in
  [docs/backtest-log.md](docs/backtest-log.md).
- The live period started on 2026-10-25. Live numbers are quoted only after 56 scored days; until then there are none.

## Results

Run `test-v1` (730 origins, 17,520 hourly values per model); details and the provenance of every number in
[docs/backtest.md](docs/backtest.md). CRPS and MAE in MWh per hour; CRPS is the grid approximation from the 19
quantiles (2/(K+1) times the sum of pinball losses), not the exact integral.

| Model | CRPS | MAE | Coverage 80 % | Coverage 90 % |
|---|---:|---:|---:|---:|
| lgbm_cqr | 1,201.6 | 1,686.3 | 0.801 | 0.898 |
| lgbm_qr (no calibration) | 1,265.0 | 1,686.3 | 0.529 | 0.654 |
| mstl_ets | 1,696.2 | 2,208.6 | 0.891 | 0.937 |
| naive_week | 2,071.1 | 2,781.7 | 0.774 | 0.863 |
| Operators' reference (411), see caveat | 1,355.9 | 1,893.4 | 0.770 | 0.870 |

- H1 (beats `naive_week` and `mstl_ets`): supported. CRPS 1,201.6 against 2,071.1 for `naive_week` (-42.0 %) and
  1,696.2 for `mstl_ets`; one-sided Diebold-Mariano p-values 6.7e-17 and 6.2e-13.
- H2 (coverage within ±2 points and better than without calibration): supported. 0.801 and 0.898 against 0.529 and
  0.654 without calibration.
- H3 (weather helps, from 2025): supported, but as a sub-period result only. On the 638 origins from 2025-01-01 the
  CRPS is 1,118.3 with weather against 1,201.8 without (-6.9 %). The weather model `lgbm_cqr_wx` exists in the
  backtest only; the live job uses no weather.
- Against the operators' reference, the CRPS of `lgbm_cqr` is 11.4 % lower (1,201.6 against 1,355.9). **Series 411
  caveat:** the reference is SMARD filter 411, treated here as the operators' day-ahead forecast. That assignment was
  checked against a single hourly value of the SMARD chart; publication time and vintage are unknown, and the
  reference may hold information the model does not have at issue time. Its quantiles (`tso_reference`) are our own
  construction from the residuals of the last 56 days, not a forecast by the operators. The comparison is a yardstick,
  not a fair contest.
- With an earlier information state (12:00 the day before, run `test-v1-noon`) the CRPS of `lgbm_cqr` rises by 1.9 %
  to 1,224.0.

## Live page

[harispaartan.github.io/netzlast-prognose](https://harispaartan.github.io/netzlast-prognose/en/): latest forecast
fan, backtest table with the caveats, reliability diagram, PIT histogram and rolling live errors. Live numbers appear
only after 56 scored days; until then the page shows the count only. Every forecast is committed to the
[`forecast-log`](https://github.com/HARISPAARTAN/netzlast-prognose/tree/forecast-log) branch before its target day and
never overwritten; format and changes of the log: [docs/live-log.md](docs/live-log.md).

## Method

- Features only from data before 00:00 Europe/Berlin on the issue day: calendar, holidays weighted by state
  population, load at D-1 to D-13.
- One LightGBM model per quantile, refitted monthly on three years; intervals are conformally calibrated over the
  last 56 forecasts.
- Rolling-origin backtest with one origin per day; CRPS, pinball loss, coverage, Winkler score, PIT and
  Diebold-Mariano tests. The figures come from the monthly-refit procedure (each month is scored by the model trained
  before it), not from the served model.
- Operation: daily live run, monthly refit as a release asset (never replaced, provenance in
  `models/refit-log.csv`), PSI drift of the lag features over 365 days, data age in `/health`.

## Data and licences

- Grid load and the TSO forecast: Bundesnetzagentur | SMARD.de, licence CC BY 4.0.
- Weather (backtest variant only): Weather data by Open-Meteo.com (https://open-meteo.com/), licence CC BY 4.0.
- State population: © Statistisches Bundesamt (Destatis), 2026. Vervielfältigung und Verbreitung, auch
  auszugsweise, mit Quellennachweis gestattet.
- Code: MIT licence.

## Quick start

Demo (offline, bundled fixture period). The package on GHCR must be public for this (see "Open items"); until then,
build the image yourself with `docker build -t netzlast-prognose .`.

```bash
docker run --rm -p 8000:8000 ghcr.io/harispaartan/netzlast-prognose:0.1.0
curl "http://127.0.0.1:8000/forecast?target_date=2025-10-26"
```

Full mode with your own data (store from `lastprog fetch`, model from `lastprog train` or the `models` release
asset):

```bash
uv sync --locked --all-extras
uv run lastprog fetch --from 2023-01-01
uv run lastprog train --as-of 2026-10-01
uv run lastprog forecast
uv run lastprog serve        # API on port 8000
```

More commands: `lastprog backtest --run-id ... --period validation|test` (the test period runs only with the tag
`protocol-v1`), `lastprog tune`, `lastprog live --log-dir <forecast-log>`, `lastprog report --log-dir <forecast-log>`,
`lastprog refit-log`, `lastprog repair-store`.

The Docker image in full mode:

```bash
docker run --rm -p 8000:8000 -e LASTPROG_MODE=full -e LASTPROG_DATA_DIR=/data \
  -v "$PWD/data/store:/data/store:ro" -v "$PWD/models:/data/models:ro" \
  ghcr.io/harispaartan/netzlast-prognose:0.1.0
```

## API

- `GET /health`: status (`ok` or `degraded`, the latter with HTTP 503), model version, git SHA and file digest of the
  model, data age (`degraded` from 48 hours).
- `GET /forecast?target_date=YYYY-MM-DD&model=lgbm_cqr`: 23 to 25 hours with median, 19 quantiles and intervals;
  `model` is `lgbm_cqr` or `naive_week`. Errors: 400 (invalid date), 404 (unknown model), 409 (data not there yet),
  503 (no model).
- `GET /models`: models with training window, features, provenance (`built_on`, `training_data`) and the test metrics
  of the backtest procedure, explicitly not an evaluation of the served model. OpenAPI at `/docs`.

## Reproducibility

`uv.lock` with a fixed cut-off date, fixed seeds, deterministic LightGBM. A rerun on the same data snapshot gave
identical results. Commands, git SHA, data hash and runtime of every run are in [docs/backtest.md](docs/backtest.md);
the protocol is in [docs/protocol.md](docs/protocol.md), deviations in [docs/backtest-log.md](docs/backtest-log.md).
The weights of the served model come from a CI run and are not byte-identical to a local retrain (see below and
[docs/model-card.md](docs/model-card.md)).

## What failed

- **Wrong CRPS approximation in the draft.** "Twice the mean pinball loss" was about 5 % above the exact value for a
  normal distribution; replaced by 2/(K+1) times the sum of pinball losses (documented before the freeze). It remains
  a grid approximation from 19 quantiles.
- **A wrong percentage in the docs.** `docs/backtest.md` gave +70.6 % for `naive_week` under the 12:00 rule; the
  figure is +0.7 % (2,085.7 against 2,071.1). The factor 100 had been applied twice, which reversed the message (the
  model loses more than the baseline). Found in review and corrected.
- **The operators' reference was presented too smoothly.** The first version of the documents called series 411 the
  operators' forecast without qualification. Only one value in the SMARD chart had been checked, and the quantiles
  are our own construction. The caveats now stand in the backtest report, the model card, ADR-003, on the page and
  above. The 11.4 % CRPS advantage is therefore no proof of being better than the operators.
- **Smoke tests before the freeze.** During a review the weather model was scored on three origins in March 2025, and
  there were timing runs with 60 origins, before `protocol-v1` was tagged. Nothing was changed or tuned as a result;
  disclosed in `docs/backtest-log.md`. "Pre-registered" holds with that qualification.
- **Tests that could not see an error.** The leak test did not catch a leak into the model fit, the service tests did
  not catch data from after the cut-off, and the live tests did not catch actuals shifted by one hour. Found by
  deliberately injected errors; fixed with tests that then fail. Early on, missing values were also scored as misses;
  they now count as missing.
- **PSI drift with a 28-day window.** The first live entry showed PSI values from 0.26 to 5.1, because the load level
  follows the season and the reference window spans three years. With 28 days the check would alert permanently: on
  weekly windows 90 to 100 % were above 0.2, against 0 % with 365 days. The window is now 365 days; the first entry
  was recomputed and keeps its original values.
- **CI weights against local weights.** The served model was trained in the refit workflow. A local retrain with the
  same code, rows and windows gives different files; the cause is unproven, the platform is the likeliest. In
  addition, re-dispatching the workflow could replace the asset under the same version. The manifest and the refit
  log now record platform, versions, run URL and a digest of the data read, and an asset is never replaced.
- **Data layer.** Fetch timestamps of the reference series were empty and overwritten on every run; a missing SMARD
  index ended the fetch silently with success. Both fixed and tested.
- **Dependencies.** statsforecast 2.1.1 does not run with pandas 3; numpy 2.5 triggers warnings in pandas 2.3. Both
  bounds are pinned.
- **Red CI on `main`.** One commit went to `main` with red CI because a new test depended on git-ignored model files;
  the next commit repaired it.
- **None of the three hypotheses failed.** That favours the procedure on these two test years and says nothing about
  live operation. The model is weak in Christmas week (CRPS 1,790.5, 80 % coverage only 0.719) and in January 2026
  (CRPS 1,958.1).

## Limitations

- No school holidays, no weather in live operation, region DE only.
- Conformal calibration assumes exchangeability, which time series lack; coverage is checked empirically.
- The weather model is cleanly comparable only on the sub-period from 2025-01-01.
- Not for grid operation or trading (see [docs/model-card.md](docs/model-card.md)).

## Roadmap

- Eight weeks of live operation, then live metrics next to the backtest values.
- Day-ahead price DE-LU with its own protocol.
- Weather in the live job after the Open-Meteo terms have been reviewed.

## Open items for the owner

1. **GHCR visibility.** New GHCR packages are private. After the tag `v0.1.0`, set the package `netzlast-prognose` to
   "Public" in the package settings so that `docker run ghcr.io/harispaartan/netzlast-prognose:0.1.0` works without a
   login.
2. **Open-Meteo terms.** Read https://open-meteo.com/en/terms before any live use of weather. Until then
   `[weather] enabled = false` stays.
3. **Eight-week wait.** Quote no live metric before 56 days are scored on `forecast-log` (with a gapless daily run, not
   before 21 December 2026). Check that the daily `Forecast` workflow keeps running; GitHub may pause schedules in
   public repositories after 60 days without activity, and the monthly refit commit counts as activity.
