# deal-resell-engine

## Ziel
Intelligenter Deal-Scanner: mydealz/preisjaeger → Geizhals + Amazon Vergleich → Netto-Profit → Telegram-Alert mit Quality Score.

## Tech-Stack
- Python 3.10+
- SQLite (lokal)
- requests + BeautifulSoup
- Geizhals via r.jina.ai Mirror
- Amazon.de via Jina Search
- systemd Timer (automatischer Poll + Retry)

## Setup
```bash
cd /home/ubuntu/projects/deal-resell-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## CLI-Befehle

### Deal-Vergleich (Hauptbefehl)
```bash
# Mit Geizhals + Amazon + Quality Score + Netto-Profit
python -m app.main market-compare --max-pages 15 --max-checks 60 --min-diff 15 --limit 20 --out text

# Telegram-Alert-Format
python -m app.main market-compare --out alert

# JSON
python -m app.main market-compare --out json
```

### Live Poll (automatisch, mit Dedup)
```bash
python scripts/live_poll.py --out alert
python scripts/live_poll.py --reset --out alert  # Reset Historie
```

### Price History
```bash
python -m app.main price-history                 # Alle Modelle
python -m app.main price-history --model "galaxy s26"  # Ein Modell
```

### Deal Pipeline Tracker
```bash
# Pipeline-Stats (letzte 30 Tage)
python -m app.main pipeline-stats

# Deals nach Stage filtern
python -m app.main pipeline-list --stage found --limit 10
python -m app.main pipeline-list --stage notified

# Deal auf nächste Stufe setzen
python -m app.main pipeline-advance --key "mydealz:galaxy s26:abc123" --stage notified
python -m app.main pipeline-advance --key "mydealz:galaxy s26:abc123" --stage bought --notes "Bestellt bei Amazon"
python -m app.main pipeline-advance --key "mydealz:galaxy s26:abc123" --stage sold --sold-price 680
```

### Price Trend Predictor
```bash
# Alle Trends (linear regression auf Preisverlauf)
python -m app.main trend

# Einzelnes Modell
python -m app.main trend --model "galaxy s26"
python -m app.main trend --model "iphone 16" --days 14 --ahead 14

# JSON Output
python -m app.main trend --out json
```

### Daily Report
```bash
# Kombinierter Tagesbericht: Trends + Pipeline + Preisbewegungen
python -m app.main daily-report

# JSON Output
python -m app.main daily-report --out json
```

### URL Health Check
```bash
# Prüfe ob Deal-URLs noch erreichbar sind
python -m app.main url-health

# Auto-archiviere abgelaufene Deals
python -m app.main url-health --auto-archive

# Nur notified Deals prüfen
python -m app.main url-health --stage notified --limit 10
```

### Retry Queue
```bash
python scripts/retry_queue.py --out text
```

### Preis-Check (einzelnes Modell)
```bash
python -m app.main price-check --model "galaxy s26" --storage 512 --provider geizhals
```

## Features

### Deal-Erkennung
- **Direktkauf**: normaler Kaufpreis
- **Vertrag**: eff. Gesamtpreis (Zuzahlung + Monate × Monatsrate)
- **Bundle**: markiert Eintausch, Cashback, Gutschein

### Preisvergleich
- **Geizhals**: Variant-Suche + Text-Fallback mit URL-Extraktion
- **Amazon.de**: Preissuche via Jina
- **Platform-Vergleich**: zeigt beide Preise + Savings %

### Profit-Berechnung
- **eBay**: 12.5% Commission + 2.49% Payment + 5.99€ Versand
- **Kleinanzeigen**: 10% Commission
- **Local**: 0% Fees
- **Risiko**: 1-5% je nach Preis
- **Netto-Profit**: nach allen Abzügen

### Quality Score (0-100)
- Profit (0-40): Netto-Profit + ROI
- Reliability (0-25): Geizhals-Match, Preisverhältnis, Quelle
- Market Position (0-20): Differenz zum Marktpreis

### Deal Pipeline Tracker
- **Lifecycle-Tracking**: found → compared → notified → bought → sold → archived
- **Conversion-Stats**: Found→Notified, Notified→Bought, Bought→Sold %
- **Top Deals**: Best-ranked by Netto-Profit über Zeitraum
- **Daily Volume**: Deals pro Tag
- **Auto-Tracking**: live_poll + market-compare tracken neue Deals automatisch

### Price Trend Predictor
- **Linear Regression**: Preisverlauf → Trend-Richtung (fallend/stabil/steigend)
- **Prognose**: Geschätzter Preis in 7 und 14 Tagen
- **Konfidenz**: 🟢 Hoch / 🟡 Mittel / 🔴 Niedrig basierend auf Datenmenge + R²
- **Kaufempfehlung**: "Warten wenn Preis fällt", "Jetzt kaufen wenn Preis steigt"
- **Daily Summary**: Trend-Prognosen im Tagesbericht integriert

### Daily Report
- **Kombiniert**: Trends + Pipeline-Stats + Preisbewegungen in einem Bericht
- **Pipeline-Integration**: Zeigt 7-Tage Deal-Pipeline Status (gefunden/benachrichtigt/gekauft/verkauft)
- **Conversion-Raten**: Wie viele Deals → Benachrichtigung → Kauf
- **Top Deal Highlight**: Bester Deal der Woche nach Netto-Profit
- **JSON-Mode**: Strukturierte Daten für Automation

### URL Health Checker
- **Parallel Checks**: HEAD-Requests mit ThreadPool (5 Worker)
- **Status Detection**: Live (200), Expired (404/5xx), Redirect, Error (Timeout)
- **Auto-Archive**: Abgelaufene Deals automatisch als 'archiviert' markieren
- **Cache**: Ergebnisse pro Stunde cachen (state/url_health.json)
- **Pipeline-Integration**: Prüft alle Pipeline-Stages oder gefilterte Subsets
- Risk (-15): Vertrag, Bundle, unrealistische Ratios
- Rating: 🔥 EXZELLENT / ✅ GUT / ⚠️ OK / ⚠️ RISIKO / ❌ SCHLECHT

### Price History
- Trackt Geizhals-Preise über Zeit
- Erkennt Allzeittiefs und Preistrends
- 90 Tage Aufbewahrung

### Automatisierung
- `deal-live-poll.timer`: alle 2h (Scraping + Vergleich + Dedup)
- `deal-retry-queue.timer`: alle 6h (Retry-Queue)

### Normalisierte Modelle
iPhone, Galaxy S/A/Z, Pixel, iPad, MacBook Air/Pro/Neo, Galaxy Tab, OnePlus Pad,
PlayStation 5/Slim/Digital/Pro, Xbox, Switch, Steam Deck, ROG Ally, Legion Go,
Apple Watch, Galaxy Watch, OnePlus Watch, AirPods, Galaxy Buds, AirTag,
ThinkPad, Surface, XPS, Kindle, DJI, GoPro

## Tests: 158 ✅
