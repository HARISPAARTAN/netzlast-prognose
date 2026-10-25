# Model Card: lgbm_cqr (Netzlast-Prognose)

Status: Entwurf aus dem Backtest test-v1; Abschnitt "Betrieb" folgt mit Version 0.1.0.

## Modelldetails

- 19 LightGBM-Quantilmodelle (0,05 … 0,95), ein globales Modell je Quantil über alle Stunden, sortiert gegen
  Kreuzungen, plus konforme Kalibrierung symmetrischer Quantilpaare über die letzten 56 Ursprünge.
- Merkmale: Kalender (Stunde, Wochentag, Fourier-Terme des Jahrestags, Zeitumstellung, Weihnachten), Feiertage
  (bundesweit, Bevölkerungsanteil, Vortag/Folgetag, Brückentag), Lastlags D-1, D-2, D-6, D-13, Tagesmittel und
  -maximum D-1, 7-Tage-Mittel, Verhältnis D-1 zu D-8.
- Hyperparameter: siehe `docs/protocol.md` Abschnitt 6. Training: 1095 Tage, monatliche Neuschätzung.
- Autor: Harithas Harikaran; Lizenz des Codes: MIT.

## Verwendungszweck

Illustration und Lehre: wie man eine Wahrscheinlichkeitsprognose ehrlich bewertet und betreibt.

## Nicht vorgesehen

Netzbetrieb, Handel, Bilanzkreismanagement oder jede Entscheidung, bei der Geld oder Versorgungssicherheit auf dem
Spiel steht.

## Einflussfaktoren

Jahreszeit, Feiertage und Brückentage, Zeitumstellung, Weihnachtswoche, Strukturbrüche (2020 Lockdown, Rückgang
2022/23, wachsende Eigenerzeugung hinter dem Zähler).

## Metriken (test-v1, 2024-10-01 bis 2026-09-30)

CRPS und MAE in MWh je Stunde, MAPE in Prozent; 730 Ursprünge, 17 520 Stundenwerte je Modell.

| Modell | CRPS | MAE | MAPE | Abdeckung 80 % | Abdeckung 90 % |
|---|---:|---:|---:|---:|---:|
| lgbm_cqr | 1,201.6 | 1,686.3 | 3.177 | 0.801 | 0.898 |
| lgbm_qr | 1,265.0 | 1,686.3 | 3.177 | 0.529 | 0.654 |
| naive_week | 2,071.1 | 2,781.7 | 5.287 | 0.774 | 0.863 |
| mstl_ets | 1,696.2 | 2,208.6 | 4.226 | 0.891 | 0.937 |
| tso_reference | 1,355.9 | 1,893.4 | 3.589 | 0.770 | 0.870 |

Schnitte nach Jahr, Feiertag, Brückentag, Zeitumstellung und Weihnachtswoche: `docs/backtest.md`, Abschnitt
"Schnitte". Die drei schwächsten Schnitte von `lgbm_cqr` nach CRPS (unter Jahr, Wochentag, Feiertag, Brückentag,
Zeitumstellung und Weihnachtswoche): Weihnachtswoche (CRPS 1,790.5, n = 384), Feiertag (CRPS 1,337.9, n = 528), Donnerstag (CRPS 1,287.1, n = 2520). Der schwächste Monat ist 2026-01 (CRPS 1,958.1).

## Trainings- und Evaluationsdaten

SMARD Filter 410 (DE, stündlich) ab 2018; Evaluation als rollierender Backtest mit täglichen Ursprüngen, Protokoll
vor der Auswertung eingefroren (`protocol-v1`).

## Hinweise und bekannte Schwächen

- Keine Schulferien als Merkmal.
- Konforme Kalibrierung ohne Austauschbarkeit: Abdeckung kann in Regimewechseln abweichen (siehe Monatswerte).
- Feiertage mit kleinem Bevölkerungsanteil und Brückentage sind selten; die Schätzungen dort sind unsicher.
- Die Referenz der Netzbetreiber ist im Mittel schlechter (CRPS 1,355.9 gegen 1,201.6). Sie beruht auf SMARD
  Filter 411 ("Prognostizierter Stromverbrauch"), hier als Day-ahead-Prognose der Netzbetreiber behandelt; die
  Zuordnung wurde nur an einem einzigen Stundenwert des SMARD-Diagramms geprüft, Veröffentlichungszeit und Fassung
  (Vintage) sind unbekannt. Die Quantile dieser Referenz (`tso_reference`) sind unsere eigene Konstruktion aus den
  Residuen der letzten 56 Tage, keine Prognose der Netzbetreiber.
- Der CRPS ist die Gitternäherung aus 19 Quantilen (siehe `docs/backtest.md`).

## Herkunft der ausgelieferten Gewichte

Die ausgelieferten Modelldateien (Version 2026.10.0) stammen aus dem Refit-Workflow auf einem GitHub-Runner
(`ubuntu-24.04`), nicht aus einem lokalen Lauf. Ein lokales Nachtraining mit demselben Code, denselben Merkmalen,
Zeilen und Fenstern (`--as-of 2026-10-01`, Windows 11) liefert andere Dateien: keine der 20 Modelldateien ist
byte-gleich, die Kalibrierungswerte weichen um bis zu 1,6 % ab, der Median liegt bei Stunde 12 innerhalb von 0,2 %.
Die Ursache ist nicht nachgewiesen; die wahrscheinlichste Erklärung ist die Plattform (Betriebssystem, Bibliotheks-
builds), geprüft wurde das nicht. Deshalb halten Manifest und `models/refit-log.csv` ab der nächsten Neuschätzung
Plattform, Python-, LightGBM- und NumPy-Version, die Actions-Lauf-URL und einen Digest der tatsächlich gelesenen
Lastdaten fest; ein Modell-Asset wird nie ersetzt (`docs/live-log.md`). Die Zahlen von test-v1 beschreiben das
Verfahren der monatlichen Neuschätzung, nicht diese Dateien.
