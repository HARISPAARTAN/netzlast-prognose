# Datennotizen

## Quellen

- SMARD (Bundesnetzagentur), Chart-API `https://www.smard.de/app/chart_data/{filter}/{region}/index_hour.json` und
  `.../{filter}_{region}_hour_{chunk_ms}.json`. Filter 410 = Stromverbrauch Gesamt (Netzlast, Ziel), Filter 411 =
  prognostizierter Stromverbrauch (Referenz der Übertragungsnetzbetreiber, nie ein Merkmal). Region `DE`, Auflösung
  `hour`, Einheit MWh je Stunde. Lizenz: CC BY 4.0, Nennung "Bundesnetzagentur | SMARD.de".
- Open-Meteo Previous Runs API, Variablen `temperature_2m_previous_day2` und `shortwave_radiation_previous_day2`
  (Wert des Laufs 48 Stunden vor der Gültigkeitszeit), Daten ab 2024-01-20 12:00 UTC, acht Städte aus
  `data/seed/staedte.csv`. Nur im Backtest. Lizenz: CC BY 4.0, "Weather data by Open-Meteo.com"
  (https://open-meteo.com/). Dokumentation: https://open-meteo.com/en/docs und
  https://open-meteo.com/en/docs/previous-runs-api.
- Destatis, Bevölkerung am 31.12.2025 nach Bundesländern (Stand 16. Juni 2026), Summe 83.467.117, als Gewichte für
  regionale Feiertage und Wetterpunkte. "© Statistisches Bundesamt (Destatis), 2026. Vervielfältigung und
  Verbreitung, auch auszugsweise, mit Quellennachweis gestattet."

## Prüfungen (scripts/verify_sources.py)

```text
Checked 2026-10-25 06:40 UTC with scripts/verify_sources.py.

- 410 DE hour: 617 weekly chunks, 2014-12-28T23:00Z to 2026-10-18T22:00Z
- 410 DE-LU hour: 421 weekly chunks, 2018-09-30T22:00Z to 2026-10-18T22:00Z
- 411 DE hour: 617 weekly chunks, 2014-12-28T23:00Z to 2026-10-18T22:00Z
- Week of 2025-10-19T22:00Z: hourly chunk 169 rows, quarter-hour chunk 676 rows; hourly value = sum of its four quarter-hours (largest difference 0.0100 MWh)
- 411 against 410 in that week: MAPE 3.81 % over 169 hours
- Chart check, Monday 2025-10-20 12:00 local: 410 = 66,381.39 MWh, 411 = 65,858.75 MWh
- Newest values now: 410 up to 2026-10-25T05:00Z, 411 up to 2026-10-25T22:00Z (411 runs ahead of the realised load, as a day-ahead forecast must)
- Open-Meteo Previous Runs: variable `temperature_2m_previous_day2` exists; first value 2024-01-20T12:00 UTC
- Locked versions: lightgbm 4.7.0, statsforecast 2.1.1, holidays 0.107, pandas 2.3.3, numpy 2.4.6, fastapi 0.150.0, scipy 1.18.1, matplotlib 3.11.2
```

Filter 410 ist für Region `DE` in Stundenauflösung verfügbar; ein Rückgriff auf `DE-LU` war nicht nötig.

Chart check: bestanden. Das SMARD-Diagramm (Marktdaten visualisieren, "Prognostizierter Stromverbrauch", Land
Deutschland, Auflösung Stunde, Tabellenansicht) zeigt für Montag 2025-10-20 12:00 bis 13:00 Ortszeit 65.858,75 MWh;
das entspricht dem Wert von Filter 411 (65,858.75 MWh) ohne Abweichung. Geprüft am 2026-10-25 im Browser. Der
Wert von Filter 410 wurde im Diagramm nicht gegengelesen.

## Beobachtungen

- Ein SMARD-Chunk deckt eine lokale Woche ab Montag 00:00 Europe/Berlin ab (168, 167 oder 169 Stunden); Werte
  sind Summen der vier Viertelstunden. Fehlende Werte sind `null` und bleiben im Store `NaN`, nie 0.
- 411 wird vorab veröffentlicht: der neueste 411-Wert liegt am Ende des laufenden lokalen Tages, der neueste
  410-Wert etwa zwei Stunden vor dem Abruf. Der Live-Job protokolliert die Verzögerung in `freshness.csv`.
- Vollabruf seit 2018-01-01 (Abruf am 2026-10-25, 06:44 bis 07:01 UTC): 922 HTTP-Aufrufe (2 Indexabrufe und 920
  Chunks, je 460 für 410 und 411) in rund 16,5 Minuten, Rohcache 7,5 MB in 920 Dateien, `observations.parquet`
  1,8 MB mit 154.560 Zeilen. Last (410): 77.263 Werte von 2017-12-31 23:00 UTC bis 2026-10-25 05:00 UTC, keine
  Lücken; die 17 Nullwerte am Ende liegen in der Zukunft (laufende Woche) und bleiben `NaN`. Referenz (411): 77.256
  Werte bis 2026-10-25 22:00 UTC, 24 fehlende Stunden.
- Wetter: 8 Aufrufe (eine Stadt je Aufruf, 2024-01-01 bis 2026-09-30), Rohcache 5,9 MB, `weather.parquet` 1,4 MB,
  385.536 Zeilen (8 Städte, 2 Variablen, 2024-01-01 00:00 bis 2026-09-30 23:00 UTC), 1,94 % fehlende Werte (vor dem
  Datenbeginn am 2024-01-20).

## Zeitstempel der Variablen

- SMARD: `ts_utc` ist der Beginn der Stunde in UTC, der Wert gilt für [t, t+1 h). Der Chart-Check (Montag
  12:00 bis 13:00 Ortszeit) bestätigt das.
- Wetter (Open-Meteo, `timezone=GMT`): Momentanwerte wie `temperature_2m` gelten zum gestempelten Zeitpunkt t.
  `shortwave_radiation` ist dagegen das Mittel der vorangegangenen Stunde und gilt für (t-1 h, t]. Die Doku
  (https://open-meteo.com/en/docs, abgerufen 2026-10-25) sagt: "Most weather variables are given as an
  instantaneous value for the indicated hour", `shortwave_radiation` hat die Gültigkeit "Preceding hour mean"
  ("Shortwave solar radiation as average of the preceding hour"). Das ist bestätigt, für die `_previous_day2`-
  Variante gilt dieselbe Definition (nicht separat geprüft, die Doku führt keine abweichende auf).
- Folge für die Merkmale: Die Last der Stunde [t, t+1 h) und die Strahlung desselben Zeitraums liegen im Store
  bei `ts_utc` t+1 h. Die Merkmalsaufgabe muss die Strahlung um eine Stunde verschieben (Wert von t+1 h für die
  Lastzeile t) oder die Konvention ausdrücklich festhalten. Die gespeicherten Daten sind unverändert.
- Warum zwei Tage Vorlauf (`previous_day2`) und nicht einen: Die Prognose wird um 07:00 UTC an Tag D für den
  lokalen Tag D+1 erstellt (bis etwa 40 Stunden Vorlauf), Informationsstand ist lokal Mitternacht von D. Ein
  `previous_day1`-Wert für den Abend von D+1 stammt aus einem Lauf nach diesem Stichtag und wäre ein Leck.
- Lücke in 411: die 24 fehlenden Stunden sind der lokale Tag 2020-01-31 (2020-01-30 23:00 bis 2020-01-31 22:00 UTC).

## Abrufzeit und Reparatur

- `fetched_at_utc` ist der Zeitpunkt, an dem ein Wert zuerst gespeichert oder zuletzt geändert wurde. `upsert` stempelt
  neue Zeilen selbst, unveränderte Zeilen behalten ihren Stempel, ein NaT entsteht nicht mehr.
- Ein vor dieser Korrektur geschriebener Store hat NaT bei 411 (und bei jedem späteren Update). Einmalige,
  idempotente Reparatur: `uv run lastprog repair-store` (setzt die Reparaturzeit als Stempel, die echte Abrufzeit
  ist nicht mehr bekannt; Werte und Snapshot-Hash bleiben gleich). Ein normaler `fetch` repariert ebenfalls.
- Ein fehlender oder leerer SMARD-Index (HTTP 404) lässt `lastprog fetch` mit Fehlermeldung und Exit-Code 1 enden.
