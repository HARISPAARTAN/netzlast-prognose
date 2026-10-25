### Run `test-v1`

Command: `lastprog backtest --run-id test-v1 --period test`  
Git SHA: `91470fc764a81507332c9857203e8e09f8a21d49` · store snapshot: `5a0c9ddb2597823fb53b28cda64c9e8cadd1a2e91a21f1991e13c1c202d1488d` · config: `c560f7dd38433589` · runtime: 694 s · seed 20261025 · origins 2024-10-01 to 2026-09-30 · cut-off rule `local_midnight_of_issue_day`

| model | crps | pinball | mae | rmse | mape | mase | cov_50 | cov_80 | cov_90 | width_80 | winkler_80 | n_origins |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lgbm_cqr | 1,201.6 | 632.4 | 1,686.3 | 2,207.3 | 3.177 | 0.606 | 0.501 | 0.801 | 0.898 | 5,516.3 | 7,738.3 | 730 |
| lgbm_qr | 1,265.0 | 665.8 | 1,686.3 | 2,207.3 | 3.177 | 0.606 | 0.286 | 0.529 | 0.654 | 3,064.3 | 9,162.6 | 730 |
| lgbm_cqr_dp | 1,200.8 | 632.0 | 1,686.3 | 2,207.3 | 3.177 | 0.606 | 0.504 | 0.798 | 0.898 | 5,567.9 | 7,701.9 | 730 |
| lgbm_aci | 1,202.2 | 632.8 | 1,686.3 | 2,207.3 | 3.177 | 0.606 | 0.502 | 0.803 | 0.902 | 5,568.3 | 7,749.2 | 730 |
| lgbm_cqr_wx | 1,130.1 | 594.8 | 1,583.3 | 2,070.4 | 2.983 | 0.569 | 0.501 | 0.800 | 0.898 | 5,226.2 | 7,268.1 | 730 |
| mstl_ets | 1,696.2 | 892.8 | 2,208.6 | 3,150.0 | 4.226 | 0.794 | 0.674 | 0.891 | 0.937 | 9,738.3 | 12,362.9 | 730 |
| naive_week | 2,071.1 | 1,090.0 | 2,781.7 | 4,107.5 | 5.287 | 1.000 | 0.487 | 0.774 | 0.863 | 7,961.0 | 14,831.4 | 730 |
| naive_day | 4,532.2 | 2,385.4 | 6,217.4 | 8,077.8 | 11.954 | 2.235 | 0.501 | 0.800 | 0.897 | 22,272.4 | 28,891.8 | 730 |
| tso_reference | 1,355.9 | 713.7 | 1,893.4 | 2,459.0 | 3.589 | 0.681 | 0.470 | 0.770 | 0.870 | 5,715.7 | 8,804.9 | 730 |

| model | rows | excluded (NaN target or quantile) | unadjusted (NaN grid) | missing target |
|---|---:|---:|---:|---:|
| lgbm_cqr | 17520 | 0 | 0 | 0 |
| lgbm_qr | 17520 | 0 | 0 | 0 |
| lgbm_cqr_dp | 17520 | 0 | 0 | 0 |
| lgbm_aci | 17520 | 0 | 0 | 0 |
| lgbm_cqr_wx | 17520 | 0 | 0 | 0 |
| mstl_ets | 17520 | 0 | 0 | 0 |
| naive_week | 17520 | 0 | 0 | 0 |
| naive_day | 17520 | 0 | 0 | 0 |
| tso_reference | 17520 | 0 | 0 | 0 |

| Diebold-Mariano (daily CRPS) | mean diff | statistic | p two-sided | p (A better) | n |
|---|---:|---:|---:|---:|---:|
| lgbm_cqr vs lgbm_aci | -0.6 | -2.209 | 0.0275 | 0.0138 | 730 |
| lgbm_cqr vs lgbm_cqr_dp | 0.8 | 0.979 | 0.3278 | 0.8361 | 730 |
| lgbm_cqr vs lgbm_cqr_wx | 71.4 | 7.693 | 0.0000 | 1.0000 | 730 |
| lgbm_cqr vs lgbm_qr | -63.4 | -9.736 | 0.0000 | 0.0000 | 730 |
| lgbm_cqr vs mstl_ets | -494.7 | -7.228 | 0.0000 | 0.0000 | 730 |
| lgbm_cqr vs naive_day | -3,330.6 | -44.149 | 0.0000 | 0.0000 | 730 |
| lgbm_cqr vs naive_week | -869.6 | -8.471 | 0.0000 | 0.0000 | 730 |
| lgbm_cqr vs tso_reference | -154.4 | -3.896 | 0.0001 | 0.0001 | 730 |

| Hypothesis | supported | detail |
|---|---|---|
| H1 | yes | `{"mstl_ets": {"p_a_better": 6.18260677286609e-13, "supported": true}, "naive_week": {"p_a_better": 6.705718177830682e-17, "supported": true}}` |
| H2 | yes | `{"80": {"gap_cqr": 0.0005136986301369495, "gap_qr": 0.27083333333333337, "ok": true}, "90": {"gap_cqr": 0.002111872146118743, "gap_qr": 0.24560502283105023, "ok": true}}` |
| H3 | yes | `{"mean_diff": -83.46755108217538, "n": 638, "p_a_better": 7.099507114028975e-20, "p_two_sided": 1.419901422805795e-19, "statistic": -9.353541017329286}` |
