# ADR-002: Ziel und Produkt: stündliche Netzlast DE für den nächsten lokalen Tag

Status: angenommen (2026-10-25)

## Kontext

SMARD liefert die Netzlast als Filter 410 in Viertelstunden und Stunden; die Prognose der Netzbetreiber (411) gibt
es stündlich für die Region DE. Der Day-ahead-Markt schließt um 12:00 am Vortag.

## Entscheidung

Ziel ist die stündliche Netzlast der Region DE in MWh je Stunde. Eine Prognose pro Tag, ausgegeben um 07:00 UTC am
Tag D für den lokalen Tag D+1 (23, 24 oder 25 Stunden), 19 Quantile.

## Folgen

- Vorlaufzeiten 15 bis 40 Stunden; der Backtest bleibt auf der CPU in unter einer Stunde.
- Viertelstunden und ein 48-Stunden-Horizont bleiben Erweiterungen (`days_ahead` in der Konfiguration).
