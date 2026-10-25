# Evaluationsprotokoll v1 (vorregistriert)

Stand: eingefroren mit dem Git-Tag `protocol-v1`, bevor ein Modell auf dem Testzeitraum bewertet wurde. Jede spätere
Änderung steht mit Datum und Grund in `docs/backtest-log.md`.

## 1. Frage

Liefert eine LightGBM-Quantilregression mit konformer Kalibrierung (`lgbm_cqr`) für die stündliche Netzlast des
nächsten lokalen Tages bessere und besser kalibrierte Wahrscheinlichkeitsprognosen als einfache Baselines, und wie
groß ist der Abstand zur veröffentlichten Prognose der Übertragungsnetzbetreiber?

## 2. Daten

- Ziel: SMARD Filter 410, Region DE, Auflösung `hour`, MWh. Referenz: Filter 411 (nie ein Merkmal).
- Datenstand der Läufe: Store-Hash `5a0c9ddb2597823fb53b28cda64c9e8cadd1a2e91a21f1991e13c1c202d1488d` (SHA-256 des
  sortierten Parquet-Inhalts); die Testläufe verwenden denselben Abruf und nennen ihren Hash in `run.json`.
- Wetter (nur Variante `lgbm_cqr_wx`): Open-Meteo Previous Runs, `_previous_day2`, acht Städte, gewichtet mit der
  Bevölkerung ihres Landes.

## 3. Prognoseprodukt

Ausgabe 07:00 UTC am Tag D für den lokalen Tag D+1 (23, 24 oder 25 Stunden). Informationsstand: Lastwerte mit
Zeitstempel vor 00:00 Europe/Berlin am Tag D (`local_midnight_of_issue_day`). 19 Quantile 0,05 bis 0,95.

## 4. Zeiträume und Ursprünge

- Validierung 2023-10-01 bis 2024-09-30: nur für Tuning und Baseline-Prüfung.
- Test 2024-10-01 bis 2026-09-30: ein Ursprung pro Tag, 730 Ursprünge.
- Wetter-Teilzeitraum: Ursprünge ab 2025-01-01.
- Vorlauf: 57 Ursprünge vor dem ersten bewerteten Ursprung füllen die Kalibrier- und Residuenfenster; sie werden
  nie bewertet.
- LightGBM wird am ersten Ursprung des Laufs und am ersten Ursprung jedes Monats neu trainiert (1095 Tage Fenster).

## 5. Modelle

| Name | Beschreibung |
|---|---|
| `naive_week` | Wert derselben lokalen Stunde eine Woche vor dem Zieltag; Quantile aus Residuen der letzten 56 Tage |
| `naive_day` | Wert derselben lokalen Stunde am Tag D-1; Quantile wie oben |
| `mstl_ets` | statsforecast MSTL (Saisons 24 und 168) mit AutoETS("ZZN"), 56 Tage, Neuschätzung je Ursprung |
| `lgbm_qr` | ein LightGBM-Modell je Quantil, globale Modelle über alle Stunden, Sortierung gegen Kreuzungen |
| `lgbm_cqr` | `lgbm_qr` plus konforme Kalibrierung über 56 Ursprünge (Hauptmodell) |
| `lgbm_cqr_dp` | Ablation: Kalibrierung je Tagesabschnitt (Nacht 0–5, Tag 6–17, Abend 18–23 Uhr lokal) |
| `lgbm_aci` | Ablation: adaptive konforme Inferenz, gamma 0,005 |
| `lgbm_cqr_wx` | `lgbm_cqr` mit Wettermerkmalen (nur Wetter-Teilzeitraum ausgewertet) |
| `tso_reference` | Filter 411; Quantile aus Residuen der letzten 56 Tage; externe Referenz |

## 6. Hyperparameter (eingefroren)

Tuning-Budget: höchstens 12 Einstellungen, nur auf dem Validierungsjahr, bewertet mit dem mittleren Pinball-Verlust
von `lgbm_qr` (Gitter in `src/lastprog/tuning.py`, Ergebnis in `docs/results/tuning-v1.json`).

| Parameter | Wert |
|---|---|
| n_estimators | 200 |
| learning_rate | 0.1 |
| num_leaves | 63 |
| min_child_samples | 100 |
| feature_fraction | 0.9 |
| lambda_l2 | 1.0 |
| seed / deterministic / num_threads | 20261025 / true / 4 |

## 7. Metriken

- Pinball-Verlust über das 19-Quantil-Gitter; CRPS ≈ 2/(k+1) · Σ Pinball (k = 19; Abweichung 1 unten).
- MAE, RMSE, MAPE des Medians; MASE gegen den MAE von `naive_week` auf denselben Punkten.
- Abdeckung, mittlere Breite und Winkler-Score der 50-, 80- und 90-%-Intervalle; PIT-Histogramm mit 20 Klassen.
- Gepoolt über die gemeinsamen Punkte aller Modelle außer der Referenz; die Referenz auf den gemeinsamen Punkten mit
  `naive_week`.
- Schnitte: Stunde, Wochentag, Monat, Jahr, Feiertag (Bevölkerungsanteil ≥ 0,5), Brückentag, Zeitumstellungstag,
  Weihnachtswoche (24.–31.12.).

## 8. Signifikanz

Diebold-Mariano-Test auf täglichen CRPS-Differenzen mit Harvey-Leybourne-Newbold-Korrektur und Newey-West-Varianz,
Lag 7; `lgbm_cqr` gegen jedes andere Modell, einseitiger p-Wert für "`lgbm_cqr` besser".

## 9. Hypothesen und Entscheidungsregeln

- H1: `lgbm_cqr` hat einen niedrigeren mittleren CRPS als `naive_week` und als `mstl_ets`; gestützt, wenn für beide
  der Mittelwert der Differenz negativ und der einseitige DM-p-Wert < 0,05 ist.
- H2: Die 80- und 90-%-Intervalle von `lgbm_cqr` decken über den Testzeitraum innerhalb ±2 Prozentpunkten ab, und
  näher am Nominalwert als `lgbm_qr`; gestützt, wenn beides für beide Niveaus gilt.
- H3: Wetter senkt den mittleren CRPS im Wetter-Teilzeitraum; gestützt, wenn `lgbm_cqr_wx` gegen `lgbm_cqr` eine
  negative mittlere Differenz und einen einseitigen DM-p-Wert < 0,05 hat.
- Der Abstand zu `tso_reference` wird ohne gerichtete Hypothese berichtet.

## 10. Sensitivität

Ein zweiter Testlauf `test-v1-noon` mit `lgbm_cqr` und `naive_week` und Informationsstand 12:00 lokal am Tag D-1
(`noon_of_previous_day`) zeigt die Kosten der vorsichtigen Grenze.

## 11. Reproduzierbarkeit

Feste Seeds, deterministisches LightGBM, `uv.lock` mit `exclude-newer`, Befehle:
`uv run lastprog backtest --run-id test-v1 --period test` und
`uv run lastprog backtest --run-id test-v1-noon --period test --models lgbm_cqr,naive_week --cutoff-rule noon_of_previous_day`.
Ein Wiederholungslauf auf demselben Store muss identische `summary.json` liefern.

## 12. Bekannte Abweichungen vom Design (vor dem Einfrieren)

1. CRPS-Gitter: 2/(k+1) · Σ Pinball statt "2 × mittlerer Pinball". Die Spec-Formel überschätzt den CRPS einer
   Normalverteilung um etwa 5 %; die neue ist im Mittel innerhalb 1 % (Test in `tests/test_metrics.py`) und
   unterscheidet sich nur um den konstanten Faktor 0,95, Rangfolgen und DM-Tests bleiben gleich.
2. statsforecast 2.1.1 verlangt pandas < 3; pandas 2.3.3 und numpy < 2.5 sind gepinnt.
3. Bevölkerungsgewichte vom 31.12.2025 (aktueller Destatis-Stand) statt 31.12.2024.
4. Wetter mit `_previous_day2`: für die späten Stunden von D+1 stammt der Lauf aus der Zeit nach Mitternacht von D,
   aber vor der Ausgabezeit 07:00 UTC. Die Wettergrenze ist damit die Ausgabezeit, nicht der Last-Stichtag.
5. Das Demo-Modell wird beim Docker-Build und in den Tests erzeugt, nicht eingecheckt (1,5 MB > Fixture-Grenze).
6. Die API-Tests decken 24- und 25-Stunden-Tage ab; der Fixture-Zeitraum enthält keinen 23-Stunden-Tag
   (`tests/test_timekeys_dst.py` prüft 23 Stunden auf Ebene der Zeitschlüssel).
7. Schutzvorrichtungen im Code vor dem Tag: `lastprog backtest --period test` verweigert den Lauf, solange der Tag
   `protocol-v1` fehlt oder nicht auf einem Vorfahren von HEAD liegt (Override `--allow-unprotocolled` wird
   protokolliert und setzt `protocol_v1: false` in `run.json`); `run.json` und `tuning-v1.json` tragen ein
   `git_dirty`-Feld; Leck-Tests prüfen auch die Modellanpassung an einem Monatsanfang und am ersten Ursprung.
8. Das Validierungsjahr (`val-v1`) wurde mit den Ausgangswerten der Hyperparameter (400 Bäume, Lernrate 0,05, 31
   Blätter, 50 Mindestproben) bewertet, vor dem Tuning; `tuning-v1.json` enthält die Tuning-Ergebnisse.
9. Der Store reicht für die Last bis 2026-10-25, das Wetter bis 2026-09-30; bewertet wird nur bis 2026-09-30, der
   Zeitraum danach (Live) bleibt unbewertet.
