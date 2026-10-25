# ADR-003: Informationsstand Mitternacht und die Netzbetreiber-Prognose als externe Referenz

Status: angenommen (2026-10-25)

## Kontext

SMARD dokumentiert die Veröffentlichungsverzögerung der Ist-Last nicht. Gemessen am 2026-10-25 lag der neueste
Wert etwa zwei Stunden zurück. Filter 411 ("Prognostizierter Stromverbrauch") wird hier als Day-ahead-Prognose der
Netzbetreiber behandelt. Diese Zuordnung wurde nur an einem einzigen Wert des SMARD-Diagramms geprüft
(`docs/data-notes.md`); Erzeuger, Veröffentlichungszeit und Fassung (Vintage) der Historie sind unbekannt. Die Reihe
enthält womöglich Informationen, die ein Modell um 07:00 UTC nicht sicher hat. Die Quantile von `tso_reference` sind
unsere eigene Konstruktion aus den Residuen der letzten 56 Tage, keine probabilistische Prognose der Netzbetreiber.

## Entscheidung

Merkmale sehen nur Lastwerte mit Zeitstempel vor 00:00 Europe/Berlin am Ausgabetag (`cutoff_utc`, eine Funktion
für Backtest und Live-Job). Ein Sensitivitätslauf mit 12:00 am Vortag zeigt die Kosten. 411 ist nie ein Merkmal und
wird als `tso_reference` getrennt berichtet.

## Folgen

- Der Leck-Test ersetzt alle Werte ab dem Stichtag durch einen riesigen Wert und verlangt bitgleiche Merkmale.
- Der Live-Job wird bis zu 24 fehlende Stunden vor dem Stichtag tolerieren (`--max-missing-hours`), die API keine.
