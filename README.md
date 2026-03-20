# deal-resell-engine

## Ziel
Rule-based MVP, der Deals von mydealz/preisjaeger einsammelt, nach Flip-relevanten Signalen bewertet und die besten Kandidaten ausgibt.

## Tech-Stack
- Python 3.10+
- SQLite (lokal)
- requests + BeautifulSoup

## Setup (isoliert)
```bash
cd /home/ubuntu/projects/deal-resell-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Aktueller Status
- Funktionierender MVP-Pipeline-CLI:
  - `ingest --mode sample|live`
  - `report --min-score --days`
  - `backfill-normalization --limit`
  - `profit-report --min-score --days`
- Live-Intake robust mit Fallback + Cursor-Logik (`--new-only`) für Polling ohne Duplikat-Waste.
- Markdown-Fallback-Parser gehärtet: Bild-/Asset-Links werden gefiltert, echte Deal-URLs priorisiert.
- Abgelaufene Deals werden über Marker gefiltert (z. B. "abgelaufen", "expired").
- Score-Engine v2: getrennte Logik für Travel-Deals (Ziel/Baseline/Abflugorte) und Resell-Tech-Deals (Gewinn-/Idealo-/Gebrauchtpreis-Signale).
- Persistenz in SQLite (`deals.db`)
- Produktnormalisierung gestartet (Brand/Model/Storage/Color) und im DB-Schema hinterlegt
- Storage-Normalisierung verbessert: bevorzugt echte Gerätespeicher-Werte gegenüber RAM-Matches (z. B. 16GB RAM + 512GB SSD → 512GB)
- Modell-Erkennung erweitert um Varianten (z. B. iPhone Pro Max, Galaxy Ultra/Plus/FE)
- Mock-Marktpreis-Adapter + erste Profit-Schätzung (Fee/Versand/Risikoabschlag) als CLI-Report verfügbar
- Profit-Report unterstützt `--min-profit`, `--min-roi`, `--sort-by score|profit`, `--top N`, Ausgabeformat `--out text|json` und JSON-Schema `--json-schema full|alert` (alert inkl. `alert_key`, `source` + `normalized_model`)
- Marktpreis-Provider als austauschbares Interface vorbereitet (EbaySold-Stub + statische Fallback-Tabelle), auswählbar via `--provider auto|static|ebay`
- Sample-Dataset für reproduzierbare Läufe enthalten

## Start
```bash
python -m app.main ingest --mode sample
python -m app.main ingest --mode live --new-only   # nur neue Deals seit letztem Poll
python -m app.main report --min-score 55 --days 7
python -m app.main backfill-normalization --limit 500
python -m app.main profit-report --min-score 55 --days 7 --provider auto --min-profit 0 --min-roi 5 --sort-by profit --top 5 --out json --json-schema alert
```

## Hinweis zu Live-Intake
mydealz/preisjaeger können per Cloudflare blocken (HTTP 403). Der Connector ist integriert, aber robust auf Fallback ausgelegt.
Nächster Schritt ist ein legaler/stabiler Feed-Zugang (API/RSS-Zugang oder erlaubte Endpunkte).

## Nächste Schritte
1. Produktnormalisierung (Brand/Model/Storage/Color)
2. Marktpreis-Adapter (eBay sold + Ankaufportale)
3. Netto-Profit-Engine (Gebühren, Versand, Risikoabschlag)
4. Telegram Alerts nur bei Score + Profit-Schwelle
5. Vertragsmodus als eigener Parser (Einmalkosten, mtl. Kosten, Laufzeit, Boni)
