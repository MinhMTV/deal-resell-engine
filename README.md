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
- Live-Intake robust mit Fallback + Cursor-Logik (`--new-only`) für Polling ohne Duplikat-Waste.
- Abgelaufene Deals werden über Marker gefiltert (z. B. "abgelaufen", "expired").
- Rule-based Score vorhanden (`keyword + community + price bucket`) inkl. Reise/Flughafen-Keywords.
- Persistenz in SQLite (`deals.db`)
- Produktnormalisierung gestartet (Brand/Model/Storage/Color) und im DB-Schema hinterlegt
- Sample-Dataset für reproduzierbare Läufe enthalten

## Start
```bash
python app/main.py ingest --mode sample
python app/main.py ingest --mode live --new-only   # nur neue Deals seit letztem Poll
python app/main.py report --min-score 55 --days 7
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
