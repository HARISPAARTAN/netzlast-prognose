# Model Card: lgbm_cqr (Netzlast-Prognose)

Status: Version 0.1.0 (ausgeliefertes Modell 2026.10.0).

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

Belege: Die Ausgaben je Ursprung der Läufe (test-v1, test-v1-noon, die Wiederholung und val-v1), die Daten des
Protokollfensters als Parquet-Auszug und die Prüfsummen (`SHA256SUMS`) liegen als Assets am GitHub-Release v0.1.0.
Die Kennzahlen dieser Karte lassen sich daraus mit `scripts/recompute_headline.py` neu berechnen; die Daten prüft
`scripts/window_digest.py`. Befehle und der Stand der Prüfung (der Hash des Gesamtstores von damals ist nicht mehr
nachprüfbar) stehen in `docs/backtest.md`, Abschnitt "Belege und Nachprüfung".

## Hinweise und bekannte Schwächen

- Keine Schulferien als Merkmal.
- Datenstand der Serie 410: Der Backtest liest den SMARD-Verlauf, wie er am 2026-10-25 abgerufen wurde, also
  womöglich nachträglich revidierte Werte. SMARD kann die Last der letzten Tage und Wochen nach der
  Erstveröffentlichung ändern; der Live-Betrieb sieht dagegen die Erstveröffentlichung, zwei Stunden alt. Der
  Backtest ist deshalb bezüglich der Datenfassung nur näherungsweise Echtzeit. Wie groß die Revisionen sind, wurde
  nicht gemessen.
- Konforme Kalibrierung ohne Austauschbarkeit: Abdeckung kann in Regimewechseln abweichen (siehe Monatswerte).
- Feiertage mit kleinem Bevölkerungsanteil und Brückentage sind selten; die Schätzungen dort sind unsicher.
- Die Referenz der Netzbetreiber ist im Mittel schlechter (CRPS 1,355.9 gegen 1,201.6). Sie beruht auf SMARD
  Filter 411 ("Prognostizierter Stromverbrauch"), hier als Day-ahead-Prognose der Netzbetreiber behandelt; die
  Zuordnung wurde nur an einem einzigen Stundenwert des SMARD-Diagramms geprüft, Veröffentlichungszeit und Fassung
  (Vintage) sind unbekannt. Die Quantile dieser Referenz (`tso_reference`) sind unsere eigene Konstruktion aus den
  Residuen der letzten 56 Tage, keine Prognose der Netzbetreiber.
- Der CRPS ist die Gitternäherung aus 19 Quantilen (siehe `docs/backtest.md`).
- Das Wettermodell `lgbm_cqr_wx` ist nur im Backtest vorhanden. Sein Vorteil (CRPS 1,118.3 gegen 1,201.8 ohne Wetter,
  -6.9 %) ist ein Teilzeitraum-Ergebnis auf 638 Ursprüngen ab 2025-01-01; im Live-Betrieb wird kein Wetter verwendet.
- Die Zahlen von test-v1 beschreiben das Verfahren der monatlichen Neuschätzung, jeder Monat bewertet vom davor
  trainierten Modell, nicht das ausgelieferte Modell.

## Betrieb

- Ausgeliefertes Modell: Version 2026.10.0, trainiert bis 2026-09-30T22:00:00Z (`trained_until` im Manifest),
  Manifest in `models/2026.10.0/manifest.json`, Modelldateien als Release-Asset `models` (Vorabversion; Version
  2026.10.0 wurde einmal vor dem ersten Live-Eintrag ersetzt, seitdem wird kein Asset mehr ersetzt); Herkunft jeder Version in `models/refit-log.csv`.
- Dienst: FastAPI (`/health`, `/forecast`, `/models`), Docker-Image `ghcr.io/harispaartan/netzlast-prognose:0.1.0`;
  Demo-Modus mit dem Fixture-Zeitraum, voller Modus mit eingebundenem Datenverzeichnis.
- Live: täglicher Lauf 07:00 UTC seit 2026-10-25, Protokoll auf dem Branch `forecast-log` (Format:
  `docs/live-log.md`), monatliche Neuschätzung am 1. des Monats.
- Überwachung: Datenalter in `/health` (Status `degraded` ab 48 Stunden), PSI der Lag-Merkmale über die letzten 365
  Tage gegen das Trainingsfenster (Warnung über 0.2; der erste Eintrag wurde mit 28 Tagen geschrieben und neu
  berechnet), rollierender 28-Tage-CRPS und Abdeckung auf der Live-Seite.
- Live-Metriken: keine, bis 56 Tage bewertet sind (der Betrieb begann am 2026-10-25). Bis dahin zeigt die Seite nur
  die Anzahl bewerteter Tage.

## Herkunft der ausgelieferten Gewichte

Die ausgelieferten Modelldateien (Version 2026.10.0) stammen aus dem Refit-Workflow auf einem GitHub-Runner
(`ubuntu-24.04`), nicht aus einem lokalen Lauf. Ein lokales Nachtraining mit demselben Code, denselben Merkmalen,
Zeilen und Fenstern (`--as-of 2026-10-01`, Windows 11) liefert Dateien, die nicht byte-gleich sind. Wie groß die Abweichung der Vorhersagen ist, wurde nicht in den
Unterlagen dieses Repositorys festgehalten und wird deshalb hier nicht beziffert. Plattform, Python- und
LightGBM-Version des ausgelieferten Builds stehen in `models/refit-log.csv` (Zeile 2026.10.0).
Die Ursache ist nicht nachgewiesen; die wahrscheinlichste Erklärung ist die Plattform (Betriebssystem, Bibliotheks-
builds), geprüft wurde das nicht. Deshalb halten Manifest und `models/refit-log.csv` ab der nächsten Neuschätzung
Plattform, Python-, LightGBM- und NumPy-Version, die Actions-Lauf-URL und einen Digest der tatsächlich gelesenen
Lastdaten fest; ein Modell-Asset wird nie ersetzt (`docs/live-log.md`). Die Zahlen von test-v1 beschreiben das
Verfahren der monatlichen Neuschätzung, nicht diese Dateien.
