# Backtest-Ergebnisse v1

Protokoll: `docs/protocol.md` (Tag `protocol-v1`). Alle Zahlen stammen aus den unten genannten Läufen; jede Tabelle
nennt ihre Lauf-ID. CRPS, MAE und RMSE in MWh je Stunde, MAPE in Prozent. Zahlen mit Dezimalpunkt wie in den
Ergebnisdateien unter `docs/results/`.

## Kurzfassung

- H1 (`lgbm_cqr` schlägt `naive_week` und `mstl_ets`): gestützt
  (einseitige DM-p-Werte 6.7e-17 und 6.2e-13).
  Der CRPS von `lgbm_cqr` liegt bei 1,201.6 gegen 2,071.1 für `naive_week`
  (-42.0 %) und 1,696.2 für `mstl_ets` (Lauf test-v1).
- H2 (Abdeckung 80/90 % innerhalb ±2 Punkte und näher als `lgbm_qr`): gestützt;
  Abdeckung `lgbm_cqr` 0.801 / 0.898, `lgbm_qr`
  0.529 / 0.654.
- H3 (Wetter senkt den CRPS ab 2025-01-01): gestützt; CRPS mit Wetter
  1,118.3, ohne 1,201.8 (-6.9 %, 638 Ursprünge,
  einseitiger DM-p-Wert 7.1e-20).
- Referenz der Netzbetreiber: CRPS 1,355.9 gegen 1,201.6 für `lgbm_cqr`
  (-11.4 %; DM 0.0001 zweiseitig). Die Referenz nutzt
  Informationen, die das Modell nicht hat; sie ist ein Maßstab, kein fairer Gegner.

## Läufe

| Lauf | Zeitraum | Modelle | Befehl | Git-SHA | Store-Hash | Laufzeit |
|---|---|---|---|---|---|---|
| val-v1 | 2023-10-01 bis 2024-09-30 | naive_week, naive_day, mstl_ets, lgbm_qr, lgbm_cqr, lgbm_cqr_dp, lgbm_aci, tso_reference | `lastprog backtest --run-id val-v1 --period validation` | `9922a20072` | `5a0c9ddb2597` | 241.5 s |
| test-v1 | 2024-10-01 bis 2026-09-30 | naive_week, naive_day, mstl_ets, lgbm_qr, lgbm_cqr, lgbm_cqr_dp, lgbm_aci, tso_reference, lgbm_cqr_wx | `lastprog backtest --run-id test-v1 --period test` | `91470fc764` | `5a0c9ddb2597` | 693.9 s |
| test-v1-noon | 2024-10-01 bis 2026-09-30 | lgbm_cqr, naive_week | `lastprog backtest --run-id test-v1-noon --period test --models lgbm_cqr,naive_week --cutoff-rule noon_of_previous_day` | `91470fc764` | `5a0c9ddb2597` | 198.1 s |

Wiederholungslauf `test-v1-noon-rerun`: `summary.json` identisch mit `test-v1-noon` (byte-gleich, Vergleich der
geladenen JSON-Objekte und der Dateien). `val-v1` entstand vor dem Tuning mit den Ausgangswerten der
Hyperparameter (Git-SHA vor dem Einfrieren); `test-v1` und `test-v1-noon` laufen mit dem getaggten Stand
(`protocol_v1: true`, `git_dirty: false` in `run.json`).

Bewertet werden Ursprünge von 2024-10-01 bis 2026-09-30; der letzte Ursprung prognostiziert den lokalen Tag
2026-10-01. Deshalb erscheint 2026-10 in den Monatstabellen mit einem einzigen Tag (24 Stunden), und `lgbm_cqr_wx`
hat für diesen Tag höchstens zwei Stunden Wetter (der Wetterstore endet am 2026-09-30 23:00 UTC).

## Testzeitraum (test-v1)

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

MASE ist hier der MAE des Modells geteilt durch den MAE von `naive_week` auf denselben Punkten, nicht die
Skalierung mit dem Fehler im Trainingsstück nach Hyndman und Koehler.

## Sensitivität: Informationsstand 12:00 am Vortag (test-v1-noon)

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

Der CRPS von `lgbm_cqr` ändert sich gegenüber test-v1 um +1.9 % (1,224.0
gegen 1,201.6); der von `naive_week` um +70.6 %. Unter dieser Regel ist der Tag D-1 nur
zur Hälfte beobachtet, `lag_d1` fehlt für die Stunden 12 bis 23, und die Tagesstatistiken beruhen auf dem Halbtag.

## Validierungsjahr (val-v1, vor dem Tag)

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

## Schnitte (test-v1)

Wochentag 0 = Montag; Monate nach Zieltag. Feiertag: Bevölkerungsanteil ≥ 0.5.

| year | lgbm_cqr n | lgbm_cqr CRPS | lgbm_cqr cov80 | naive_week n | naive_week CRPS | naive_week cov80 | tso_reference n | tso_reference CRPS | tso_reference cov80 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024 | 2185 | 1,186.6 | 0.795 | 2185 | 2,238.3 | 0.752 | 2185 | 1,559.7 | 0.692 |
| 2025 | 8760 | 1,155.6 | 0.799 | 8760 | 1,970.9 | 0.765 | 8760 | 1,261.9 | 0.769 |
| 2026 | 6575 | 1,267.8 | 0.805 | 6575 | 2,149.1 | 0.793 | 6575 | 1,413.5 | 0.798 |

| weekday | lgbm_cqr n | lgbm_cqr CRPS | lgbm_cqr cov80 | naive_week n | naive_week CRPS | naive_week cov80 | tso_reference n | tso_reference CRPS | tso_reference cov80 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2496 | 1,225.1 | 0.790 | 2496 | 2,282.8 | 0.756 | 2496 | 1,347.4 | 0.787 |
| 1 | 2496 | 1,250.8 | 0.798 | 2496 | 1,716.6 | 0.813 | 2496 | 1,287.5 | 0.815 |
| 2 | 2520 | 1,153.2 | 0.834 | 2520 | 1,820.2 | 0.831 | 2520 | 1,393.0 | 0.763 |
| 3 | 2520 | 1,287.1 | 0.780 | 2520 | 2,740.1 | 0.692 | 2520 | 1,487.3 | 0.704 |
| 4 | 2496 | 1,182.3 | 0.806 | 2496 | 2,835.8 | 0.651 | 2496 | 1,276.8 | 0.796 |
| 5 | 2496 | 1,140.5 | 0.795 | 2496 | 1,555.3 | 0.841 | 2496 | 1,250.7 | 0.802 |
| 6 | 2496 | 1,171.7 | 0.800 | 2496 | 1,542.8 | 0.833 | 2496 | 1,447.4 | 0.726 |

| holiday | lgbm_cqr n | lgbm_cqr CRPS | lgbm_cqr cov80 | naive_week n | naive_week CRPS | naive_week cov80 | tso_reference n | tso_reference CRPS | tso_reference cov80 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| False | 16992 | 1,197.4 | 0.799 | 16992 | 1,902.5 | 0.791 | 16992 | 1,354.0 | 0.771 |
| True | 528 | 1,337.9 | 0.864 | 528 | 7,495.8 | 0.227 | 528 | 1,418.8 | 0.752 |

| bridge | lgbm_cqr n | lgbm_cqr CRPS | lgbm_cqr cov80 | naive_week n | naive_week CRPS | naive_week cov80 | tso_reference n | tso_reference CRPS | tso_reference cov80 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| False | 17328 | 1,200.8 | 0.800 | 17328 | 2,043.0 | 0.779 | 17328 | 1,348.7 | 0.772 |
| True | 192 | 1,272.2 | 0.854 | 192 | 4,607.6 | 0.354 | 192 | 2,005.6 | 0.630 |

| dst_day | lgbm_cqr n | lgbm_cqr CRPS | lgbm_cqr cov80 | naive_week n | naive_week CRPS | naive_week cov80 | tso_reference n | tso_reference CRPS | tso_reference cov80 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| False | 17424 | 1,201.4 | 0.800 | 17424 | 2,073.8 | 0.774 | 17424 | 1,357.0 | 0.770 |
| True | 96 | 1,232.3 | 0.823 | 96 | 1,575.1 | 0.812 | 96 | 1,159.9 | 0.885 |

| xmas_week | lgbm_cqr n | lgbm_cqr CRPS | lgbm_cqr cov80 | naive_week n | naive_week CRPS | naive_week cov80 | tso_reference n | tso_reference CRPS | tso_reference cov80 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| False | 17136 | 1,188.4 | 0.802 | 17136 | 2,002.1 | 0.780 | 17136 | 1,336.9 | 0.775 |
| True | 384 | 1,790.5 | 0.719 | 384 | 5,149.9 | 0.492 | 384 | 2,206.3 | 0.570 |

| month | lgbm_cqr CRPS | naive_week CRPS | tso_reference CRPS |
|---|---:|---:|---:|
| 2024-10 | 900.8 | 1,908.1 | 908.0 |
| 2024-11 | 1,293.7 | 1,777.3 | 2,028.9 |
| 2024-12 | 1,359.9 | 3,004.4 | 1,737.1 |
| 2025-01 | 1,606.4 | 3,003.7 | 1,221.3 |
| 2025-02 | 1,329.9 | 1,948.1 | 1,145.7 |
| 2025-03 | 1,200.7 | 1,752.7 | 1,559.0 |
| 2025-04 | 1,080.2 | 2,425.7 | 1,482.5 |
| 2025-05 | 959.3 | 2,440.8 | 1,100.7 |
| 2025-06 | 1,126.7 | 2,706.9 | 1,250.9 |
| 2025-07 | 820.2 | 1,082.4 | 948.5 |
| 2025-08 | 856.5 | 946.8 | 1,191.9 |
| 2025-09 | 958.4 | 1,054.9 | 1,118.8 |
| 2025-10 | 1,280.2 | 2,057.8 | 1,320.7 |
| 2025-11 | 1,272.5 | 1,684.9 | 1,296.1 |
| 2025-12 | 1,387.2 | 2,542.5 | 1,499.5 |
| 2026-01 | 1,958.1 | 3,411.8 | 1,863.2 |
| 2026-02 | 1,306.3 | 2,273.6 | 1,498.3 |
| 2026-03 | 1,456.2 | 2,224.9 | 1,835.9 |
| 2026-04 | 1,436.6 | 2,834.8 | 1,705.2 |
| 2026-05 | 1,024.1 | 2,785.6 | 1,228.3 |
| 2026-06 | 904.2 | 1,742.9 | 1,276.4 |
| 2026-07 | 1,126.8 | 1,329.2 | 1,219.2 |
| 2026-08 | 1,192.5 | 1,527.1 | 1,039.6 |
| 2026-09 | 990.9 | 1,239.3 | 1,011.6 |
| 2026-10 | 1,368.7 | 1,040.7 | 2,792.2 |

| hour (local) | lgbm_cqr CRPS | naive_week CRPS | tso_reference CRPS |
|---|---:|---:|---:|
| 00 | 1,047.0 | 1,575.2 | 1,060.3 |
| 01 | 1,009.1 | 1,562.8 | 1,054.4 |
| 02 | 992.8 | 1,559.4 | 1,038.9 |
| 03 | 960.1 | 1,549.0 | 1,019.5 |
| 04 | 953.3 | 1,567.4 | 991.8 |
| 05 | 997.1 | 1,731.3 | 1,064.1 |
| 06 | 1,095.6 | 2,140.2 | 1,351.9 |
| 07 | 1,086.5 | 2,348.8 | 1,416.5 |
| 08 | 1,099.5 | 2,355.1 | 1,342.8 |
| 09 | 1,120.5 | 2,271.6 | 1,289.3 |
| 10 | 1,262.5 | 2,367.9 | 1,490.4 |
| 11 | 1,407.6 | 2,466.9 | 1,654.4 |
| 12 | 1,509.2 | 2,581.6 | 1,757.6 |
| 13 | 1,549.3 | 2,678.7 | 1,810.3 |
| 14 | 1,559.9 | 2,645.3 | 1,764.5 |
| 15 | 1,537.6 | 2,570.6 | 1,700.1 |
| 16 | 1,459.9 | 2,428.9 | 1,667.3 |
| 17 | 1,356.6 | 2,264.7 | 1,576.8 |
| 18 | 1,220.9 | 2,076.2 | 1,367.0 |
| 19 | 1,151.3 | 1,993.0 | 1,316.0 |
| 20 | 1,124.7 | 1,889.3 | 1,277.7 |
| 21 | 1,130.2 | 1,782.4 | 1,204.1 |
| 22 | 1,119.1 | 1,681.0 | 1,191.1 |
| 23 | 1,087.8 | 1,618.8 | 1,136.0 |

## Ablationen

- Kalibrierung je Tagesabschnitt (`lgbm_cqr_dp`): CRPS 1,200.8, Abdeckung 80 %
  0.798, gegen `lgbm_cqr` 1,201.6 / 0.801.
  Der Unterschied ist nicht signifikant (DM zweiseitig 0.3278).
- Adaptive konforme Inferenz (`lgbm_aci`): CRPS 1,202.2, Abdeckung 80 % 0.803;
  `lgbm_cqr` ist im Mittel 0.6 MWh besser (DM zweiseitig
  0.0275), praktisch kein Unterschied. `lgbm_aci` überspringt Zeilen mit
  NaN-Gitter beim Anpassen von alpha (siehe `docs/backtest-log.md`).

## Leckfreiheit

- Stichtag: Lastwerte mit Zeitstempel vor 00:00 Europe/Berlin am Ausgabetag D (`cutoff_utc`), im Sensitivitätslauf
  12:00 am Tag D-1. Filter 411 ist nur in `tso_reference` ein Eingang, nie ein Merkmal.
- Tests (`tests/test_cutoff_leak.py`, `tests/test_backtest_window.py`): Alle Lastwerte ab dem Stichtag werden durch
  einen riesigen Wert ersetzt; Merkmale, Prognosen aller Modelle und die konformen Fenster müssen bitgleich bleiben.
  Das gilt auch für die Modellanpassung am ersten Ursprung eines Laufs und am Monatsanfang (Trainingszeilen enden
  vor dem Stichtag des Ursprungs).
- Konformes Fenster und Residuenfenster: nur frühere Ursprünge, deren ganzer Zieltag vor dem Stichtag liegt, also
  bis D-2 (Zieltag D-1) unter der Mitternachtsregel und bis D-3 unter `noon_of_previous_day`.
- Wetter (`lgbm_cqr_wx`): nur `_previous_day2`. Die Strahlung ist ein Mittel der vorangegangenen Stunde; der Lauf
  hinter dem letzten Strahlungswert des Zieltags liegt an einem gewöhnlichen Tag auf dem nominalen Stichtag (0 h),
  am 25-Stunden-Tag selbst und am Tag danach aber höchstens eine Stunde danach (+1 h): im Testzeitraum an
  2024-10-27, 2024-10-28, 2025-10-26 und 2025-10-27, im Wetter-Teilzeitraum an 2025-10-26 und 2025-10-27, je ein
  stündlicher Strahlungswert. Der Lauf liegt dennoch vor der Ausgabezeit 07:00 UTC; es ist eine Überschreitung der
  nominalen Regel, kein Informationsleck (Protokoll, Abweichung 4; Details in `docs/data-notes.md`). Die
  Temperatur überschreitet den Stichtag nie.

## Grenzen

- Zeitreihenfehler sind nicht austauschbar; die endliche Abdeckungsgarantie der konformen Verfahren gilt nicht,
  Abdeckung wird empirisch beurteilt.
- Keine Schulferien als Merkmal (keine lizenzierte, gepflegte Quelle geprüft).
- Die Referenz 411 nutzt Informationen, die das Modell nicht hat; sie ist kein fairer Gegner, sondern ein Maßstab.
- `lgbm_cqr_wx` trainiert über 1095 Tage, Wetter existiert erst ab 2024-01-01; in den ersten Monaten des
  Wetter-Teilzeitraums sind viele Trainingszeilen ohne Wettermerkmale (NaN). Der Vergleich H3 ab 2025-01-01 ist
  korrekt, das Wettermodell war am Anfang aber im Nachteil.
- Die Monatswerte schwanken stark (Winter am schwächsten); Abdeckung und CRPS je Schnitt stehen in den Tabellen
  oben, kleine Schnitte (Brückentage, Weihnachtswoche, Zeitumstellung) haben wenig Punkte.
- Ein einziges Tuning auf dem Validierungsjahr; der Abstand der besten Einstellungen war klein (siehe
  `docs/results/tuning-v1.json`).
