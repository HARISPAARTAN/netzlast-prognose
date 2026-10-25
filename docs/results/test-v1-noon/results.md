### Run `test-v1-noon`

Command: `lastprog backtest --run-id test-v1-noon --period test --models lgbm_cqr,naive_week --cutoff-rule noon_of_previous_day`  
Git SHA: `91470fc764a81507332c9857203e8e09f8a21d49` · store snapshot: `5a0c9ddb2597823fb53b28cda64c9e8cadd1a2e91a21f1991e13c1c202d1488d` · config: `c560f7dd38433589` · runtime: 198 s · seed 20261025 · origins 2024-10-01 to 2026-09-30 · cut-off rule `noon_of_previous_day`

| model | crps | pinball | mae | rmse | mape | mase | cov_50 | cov_80 | cov_90 | width_80 | winkler_80 | n_origins |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lgbm_cqr | 1,224.0 | 644.2 | 1,721.8 | 2,258.8 | 3.240 | 0.615 | 0.505 | 0.800 | 0.900 | 5,637.6 | 7,861.8 | 730 |
| naive_week | 2,085.7 | 1,097.7 | 2,798.2 | 4,123.6 | 5.319 | 1.000 | 0.483 | 0.772 | 0.859 | 7,960.5 | 14,929.3 | 730 |

| model | rows | excluded (NaN target or quantile) | unadjusted (NaN grid) | missing target |
|---|---:|---:|---:|---:|
| lgbm_cqr | 17520 | 0 | 0 | 0 |
| naive_week | 17520 | 0 | 0 | 0 |

| Diebold-Mariano (daily CRPS) | mean diff | statistic | p two-sided | p (A better) | n |
|---|---:|---:|---:|---:|---:|
| lgbm_cqr vs naive_week | -861.9 | -8.212 | 0.0000 | 0.0000 | 730 |

| Hypothesis | supported | detail |
|---|---|---|
| H1 | yes | `{"naive_week": {"p_a_better": 4.94079636204769e-16, "supported": true}}` |
