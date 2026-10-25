### Run `val-v1`

Command: `lastprog backtest --run-id val-v1 --period validation`  
Git SHA: `9922a2007217697e1444d10790fade62e19d572f` · store snapshot: `5a0c9ddb2597823fb53b28cda64c9e8cadd1a2e91a21f1991e13c1c202d1488d` · config: `bbb0a6d363bf458b` · runtime: 242 s · seed 20261025 · origins 2023-10-01 to 2024-09-30 · cut-off rule `local_midnight_of_issue_day`

| model | crps | pinball | mae | rmse | mape | mase | cov_50 | cov_80 | cov_90 | width_80 | winkler_80 | n_origins |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lgbm_cqr | 1,093.0 | 575.3 | 1,514.5 | 2,022.5 | 2.921 | 0.575 | 0.497 | 0.786 | 0.886 | 4,843.6 | 7,211.7 | 366 |
| lgbm_qr | 1,126.7 | 593.0 | 1,514.5 | 2,022.5 | 2.921 | 0.575 | 0.334 | 0.593 | 0.721 | 3,217.9 | 7,963.8 | 366 |
| lgbm_cqr_dp | 1,092.9 | 575.2 | 1,514.6 | 2,022.5 | 2.921 | 0.575 | 0.500 | 0.786 | 0.885 | 4,858.5 | 7,214.6 | 366 |
| lgbm_aci | 1,093.6 | 575.6 | 1,514.5 | 2,022.5 | 2.921 | 0.575 | 0.499 | 0.792 | 0.894 | 4,923.3 | 7,223.0 | 366 |
| mstl_ets | 1,615.1 | 850.1 | 2,044.8 | 3,084.2 | 3.987 | 0.777 | 0.703 | 0.904 | 0.938 | 9,385.8 | 12,259.4 | 366 |
| naive_week | 2,034.9 | 1,071.0 | 2,632.3 | 4,116.5 | 5.111 | 1.000 | 0.483 | 0.754 | 0.848 | 7,295.2 | 15,518.2 | 366 |
| naive_day | 4,790.8 | 2,521.5 | 6,563.1 | 8,532.1 | 12.711 | 2.493 | 0.497 | 0.793 | 0.895 | 23,398.1 | 30,368.0 | 366 |
| tso_reference | 1,205.2 | 634.3 | 1,674.6 | 2,208.9 | 3.266 | 0.636 | 0.478 | 0.762 | 0.864 | 4,997.2 | 7,923.6 | 366 |

| model | rows | excluded (NaN target or quantile) | unadjusted (NaN grid) | missing target |
|---|---:|---:|---:|---:|
| lgbm_cqr | 8784 | 0 | 0 | 0 |
| lgbm_qr | 8784 | 0 | 0 | 0 |
| lgbm_cqr_dp | 8784 | 0 | 0 | 0 |
| lgbm_aci | 8784 | 0 | 0 | 0 |
| mstl_ets | 8784 | 0 | 0 | 0 |
| naive_week | 8784 | 0 | 0 | 0 |
| naive_day | 8784 | 0 | 0 | 0 |
| tso_reference | 8784 | 0 | 0 | 0 |

| Diebold-Mariano (daily CRPS) | mean diff | statistic | p two-sided | p (A better) | n |
|---|---:|---:|---:|---:|---:|
| lgbm_cqr vs lgbm_aci | -0.6 | -1.914 | 0.0563 | 0.0282 | 366 |
| lgbm_cqr vs lgbm_cqr_dp | 0.1 | 0.095 | 0.9242 | 0.5379 | 366 |
| lgbm_cqr vs lgbm_qr | -33.7 | -5.203 | 0.0000 | 0.0000 | 366 |
| lgbm_cqr vs mstl_ets | -521.8 | -4.707 | 0.0000 | 0.0000 | 366 |
| lgbm_cqr vs naive_day | -3,697.3 | -37.035 | 0.0000 | 0.0000 | 366 |
| lgbm_cqr vs naive_week | -942.3 | -5.352 | 0.0000 | 0.0000 | 366 |
| lgbm_cqr vs tso_reference | -112.2 | -1.903 | 0.0578 | 0.0289 | 366 |

| Hypothesis | supported | detail |
|---|---|---|
| H1 | yes | `{"mstl_ets": {"p_a_better": 1.7872517391494661e-06, "supported": true}, "naive_week": {"p_a_better": 7.720210858537576e-08, "supported": true}}` |
| H2 | yes | `{"80": {"gap_cqr": 0.014025500910746835, "gap_qr": 0.20744535519125684, "ok": true}, "90": {"gap_cqr": 0.013729508196721363, "gap_qr": 0.17857468123861564, "ok": true}}` |
