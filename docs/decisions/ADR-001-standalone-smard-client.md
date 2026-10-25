# ADR-001: Eigener SMARD-Client statt der Datenbank des Energiewende-Monitors

Status: angenommen (2026-10-25)

## Kontext

Der Energiewende-Monitor hält SMARD-Daten in SQL Server. Sein Umfang beginnt 2023-01-01, er speichert Region
`DE-LU` in Viertelstunden, und das Lesen würde SQL Server, pyodbc und den ODBC-Treiber in CI und Service-Image
bringen. Training plus zweijähriger Test braucht Last ab 2018, und die Referenzprognose 411 gibt es für `DE`.

## Entscheidung

Ein kleiner eigener Client in `src/lastprog/smard.py`, nach dem Vorbild von
`energiewende-monitor/src/ewmonitor/smard.py` (eigener MIT-Code des Autors), ohne Import: Chunk-Index,
wöchentliche Chunks, atomare Cache-Schreibvorgänge, erneuter Abruf unvollständiger Chunks, Wiederholungen,
DST-korrekte Chunk-Enden. Speicher: Parquet unter `data/store/`.

## Folgen

- CI und Image brauchen keine Datenbank; die Tests laufen offline auf rund 90 KB Fixtures.
- Zwei Clients müssen getrennt gepflegt werden (etwa 200 Zeilen); ein gemeinsames Paket würde zwei
  Release-Zyklen koppeln und wurde verworfen.
