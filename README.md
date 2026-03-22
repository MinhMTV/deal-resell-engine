# deal-resell-engine

## Ziel
Rule-based Deal-Scanner der mydealz/preisjaeger durchsucht, mit Geizhals vergleibt und profitable Deals mit Telegram-Alert-Format ausgibt.

## Tech-Stack
- Python 3.10+
- SQLite (lokal)
- requests + BeautifulSoup
- Geizhals via r.jina.ai Mirror
- systemd Timer (automatischer Poll + Retry)

## Setup (isoliert)
```bash
cd /home/ubuntu/projects/deal-resell-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## CLI-Befehle

### Deal-Vergleich (Hauptbefehl)
```bash
# Text-Output mit Geizhals-Daten pro Deal
python -m app.main market-compare --max-pages 15 --max-checks 60 --min-diff 15 --limit 20 --out text

# Telegram-Alert-Format (Direktkauf + Vertrags-Deals getrennt)
python -m app.main market-compare --max-pages 15 --max-checks 60 --min-diff 15 --limit 20 --out alert

# JSON-Output
python -m app.main market-compare --max-pages 15 --max-checks 60 --min-diff 15 --limit 20 --out json
```

### Live Poll (mit Deduplikation)
```bash
# Automatisch — zeigt nur neue Deals die noch nicht gesendet wurden
python scripts/live_poll.py --out alert

# Reset Duplikat-Historie
python scripts/live_poll.py --reset --out alert
```

### Retry Queue (fehlgeschlagene Geizhals-Matches)
```bash
python scripts/retry_queue.py --out text
python scripts/retry_queue.py --out json --max-age 7
```

### Preis-Check (einzelnes Modell)
```bash
python -m app.main price-check --model "galaxy s26" --storage 512 --provider geizhals
```

### Profit Report
```bash
python -m app.main profit-report --min-score 55 --days 7 --provider auto --min-profit 0 --min-roi 5 --sort-by profit --top 5 --out json --json-schema alert
```

## Features

### Deal-Erkennung
- **Direktkauf-Deals**: normaler Kaufpreis
- **Vertrags-Deals**: erkennt `X€/Monat` + `Y€ Zuzahlung`, berechnet effektiven Gesamtpreis (Zuzahlung + Monate × Monatsrate)
- **Bundle-Deals**: markiert Deals mit Eintauschbonus, Cashback, Gutschein, Speicher-Upgrade

### Geizhals-Vergleich
- **Variant-Suche**: exakte URL-Matching mit Modell + Speicher
- **Text-Fallback**: wenn Variant-Suche nichts findet, extrahiert Preise aus Suchergebnissen + echte Produkt-URLs
- **Accessory-Filter**: Hülle, Case, Schutzglas, Ladekabel, Faltschloss etc. werden rausgefiltert
- **Brand-Guard**: AirTag muss von Apple kommen, Galaxy von Samsung, Pixel von Google

### Automatisierung
- `deal-live-poll.timer`: alle 2h → Scraping + Geizhals + Dedup + Alert
- `deal-retry-queue.timer`: alle 6h → fehlgeschlagene Geizhals-Matches nachprüfen

### Normalisierte Modelle
iPhone, Galaxy S/A/Z, Pixel, iPad, MacBook Air/Pro/Neo, Galaxy Tab, OnePlus Pad,
PlayStation 5/Slim/Digital/Pro, PS5, Xbox, Switch, Steam Deck, ROG Ally, Legion Go,
Apple Watch, Galaxy Watch, OnePlus Watch, AirPods, Galaxy Buds, AirTag,
ThinkPad, Surface, XPS, Kindle, DJI, GoPro

## Status
- **43 Tests** ✅
- **Geizhals-Provider**: Variant-Suche + Text-Fallback
- **Live-Timer**: aktiv, erste Ausführung erfolgreich
- **Output-Format**: Telegram-Alert mit Geizhals pro Deal

## Nächste Schritte
1. Weitere Normalizer-Patterns (neue Modelle beobachten)
2. eBay Sold-Listings Integration
3. Kleinanzeigen/Ankauf-Adapter
4. Telegram-Integration (automatische Alerts)
5. Multi-Quellen-Support (idealo, Amazon Preistracker)
