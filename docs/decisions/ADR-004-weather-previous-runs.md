# ADR-004: Wetter nur aus Open-Meteo Previous Runs, nur im Backtest

Status: angenommen (2026-10-25)

## Kontext

Die Historical Forecast API setzt die ersten Stunden jedes Laufs zu einer Reihe zusammen; die Werte sind fast
beobachtet und würden einen Day-ahead-Backtest schönen. Previous Runs liefert dieselben Modelle mit festem
Vorlauf (`_previous_day1` … `_previous_day7`) ab Januar 2024. Die Nutzungsbedingungen nennen "promotional
activities" als kommerziell.

## Entscheidung

Nur `_previous_day2`-Werte (48 Stunden vor der Gültigkeitszeit) für Temperatur und Globalstrahlung an acht Städten,
gewichtet mit der Landesbevölkerung. Nur im Backtest (`lgbm_cqr_wx`, Auswertung ab 2025-01-01). Der Live-Job läuft
ohne Wetter (`[weather] enabled = false`).

## Folgen

- 8 API-Aufrufe für den gesamten Backtest, weit unter den Grenzen des kostenlosen Zugangs.
- Live-Wetter erst, wenn der Eigentümer die Bedingungen gelesen und zugestimmt hat.
- Für die späten Stunden von D+1 stammt der Lauf aus der Zeit vor 07:00 UTC am Tag D, nicht vor Mitternacht
  (Abweichung 4 im Protokoll).
