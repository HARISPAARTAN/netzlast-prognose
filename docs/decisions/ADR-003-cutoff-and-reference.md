# ADR-003: Informationsstand Mitternacht und die Netzbetreiber-Prognose als externe Referenz

Status: angenommen (2026-10-25)

## Kontext

SMARD dokumentiert die Veröffentlichungsverzögerung der Ist-Last nicht. Gemessen am 2026-10-25 lag der neueste
Wert etwa zwei Stunden zurück. Filter 411 wird vorab veröffentlicht und enthält Informationen, die ein Modell um
07:00 UTC nicht sicher hat.

## Entscheidung

Merkmale sehen nur Lastwerte mit Zeitstempel vor 00:00 Europe/Berlin am Ausgabetag (`cutoff_utc`, eine Funktion
für Backtest und Live-Job). Ein Sensitivitätslauf mit 12:00 am Vortag zeigt die Kosten. 411 ist nie ein Merkmal und
wird als `tso_reference` getrennt berichtet.

## Folgen

- Der Leck-Test ersetzt alle Werte ab dem Stichtag durch einen riesigen Wert und verlangt bitgleiche Merkmale.
- Der Live-Job toleriert bis zu 24 fehlende Stunden vor dem Stichtag (`--max-missing-hours`), die API keine.
