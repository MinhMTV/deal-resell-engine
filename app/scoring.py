import re

from app.config import KEYWORDS, TRAVEL_AIRPORTS


TRAVEL_HINTS = ["flug", "flüge", "reise", "urlaub", "direktflug", "direktflüge", "hin und rückflug", "pauschalreise"]
PRIORITY_AIRPORTS = ["wien", "köln", "cologne", "dortmund", "weeze", "frankfurt"]

# Lightweight baseline table (stub until real travel provider integration).
TRAVEL_BASELINES_EUR = {
    "london": 95.0,
    "osaka": 1200.0,
    "tokio": 1050.0,
    "tokyo": 1050.0,
    "bangkok": 780.0,
    "new york": 520.0,
    "mallorca": 130.0,
    "barcelona": 140.0,
    "paris": 120.0,
    "dubai": 460.0,
}


def _text(deal: dict) -> str:
    return f"{deal.get('title', '')} {deal.get('description', '')}".strip().lower()


def _is_travel_deal(text: str) -> bool:
    return any(h in text for h in TRAVEL_HINTS)


def _extract_price_signal(text: str):
    m = re.search(r"(?:ab|nur|für)?\s*(\d+[\.,]?\d*)\s?€", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _extract_destination(text: str):
    m = re.search(r"nach\s+([a-zäöüß\- ]{3,30})", text)
    if not m:
        return None
    candidate = m.group(1).strip(" .,!?:;")
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate


def _lookup_baseline_for_destination(destination: str | None):
    if not destination:
        return None
    d = destination.lower()
    for k, v in TRAVEL_BASELINES_EUR.items():
        if k in d:
            return v
    return None


def _score_travel(text: str, deal: dict):
    votes = int(deal.get("votes") or 0)
    price = float(deal.get("price") or 0)

    destination = _extract_destination(text)
    baseline = _lookup_baseline_for_destination(destination)

    deal_price = price if price > 0 else (_extract_price_signal(text) or 0.0)
    savings_pct = 0.0
    if baseline and deal_price > 0:
        savings_pct = max(0.0, (baseline - deal_price) / baseline)

    airport_hits = sum(1 for a in PRIORITY_AIRPORTS if a in text)
    community = min(max(votes, 0), 300) / 3  # 0..100

    score = 0.0
    score += min(70.0, savings_pct * 100 * 1.1)
    score += min(12.0, airport_hits * 6.0)
    score += min(18.0, community * 0.18)

    reasons = [
        "type=travel",
        f"destination={destination or 'unknown'}",
        f"baseline={baseline}",
        f"deal_price={round(deal_price, 2) if deal_price else None}",
        f"savings_pct={round(savings_pct * 100, 2)}",
        f"priority_airport_hits={airport_hits}",
        f"votes={votes}",
    ]
    return round(min(100.0, score), 2), ", ".join(reasons)


def _extract_money_amount(text: str, pattern: str):
    m = re.search(pattern, text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _extract_stated_profit(text: str):
    return _extract_money_amount(text, r"(?:gewinn|profit|marge)\s*(?:ca\.?|von)?\s*(\d+[\.,]?\d*)\s?€")


def _extract_idealo_price(text: str):
    return _extract_money_amount(text, r"(?:idealo|vergleichspreis|statt)\s*(?:ca\.?|ab)?\s*(\d+[\.,]?\d*)\s?€")


def _extract_used_market_price(text: str):
    # Placeholder for future provider-backed Kleinanzeigen/eBay sold data.
    return _extract_money_amount(text, r"(?:kleinanzeigen|gebraucht|ebay)\s*(?:ca\.?|ø|durchschnitt)?\s*(\d+[\.,]?\d*)\s?€")


def _score_resell(text: str, deal: dict):
    votes = int(deal.get("votes") or 0)
    price = float(deal.get("price") or 0)

    keyword_hits = sum(1 for k in KEYWORDS if k in text)

    stated_profit = _extract_stated_profit(text)
    idealo_price = _extract_idealo_price(text)
    used_market_price = _extract_used_market_price(text)

    buy_price = price if price > 0 else (_extract_price_signal(text) or 0.0)

    # Prefer used/private market reality; fallback to idealo reference.
    resale_anchor = used_market_price or idealo_price

    discount_pct = 0.0
    if idealo_price and buy_price > 0:
        discount_pct = max(0.0, (idealo_price - buy_price) / idealo_price)

    profit_est = 0.0
    if stated_profit is not None:
        profit_est = max(0.0, stated_profit)
    elif resale_anchor and buy_price > 0:
        # lightweight net estimate before dedicated profit engine
        gross = resale_anchor - buy_price
        fee_risk_shipping = resale_anchor * 0.17 + 6
        profit_est = max(0.0, gross - fee_risk_shipping)

    roi_pct = (profit_est / buy_price * 100.0) if buy_price > 0 else 0.0
    community = min(max(votes, 0), 300) / 3

    score = 0.0
    score += min(55.0, profit_est * 0.45)
    score += min(20.0, roi_pct * 0.4)
    score += min(10.0, discount_pct * 100 * 0.3)
    score += min(10.0, keyword_hits * 2.0)
    score += min(5.0, community * 0.05)

    reasons = [
        "type=resell",
        f"keyword_hits={keyword_hits}",
        f"buy_price={round(buy_price, 2) if buy_price else None}",
        f"stated_profit={stated_profit}",
        f"idealo_price={idealo_price}",
        f"used_market_price={used_market_price}",
        f"profit_est={round(profit_est, 2)}",
        f"roi_pct={round(roi_pct, 2)}",
        f"discount_pct={round(discount_pct * 100, 2)}",
        f"votes={votes}",
    ]
    return round(min(100.0, score), 2), ", ".join(reasons)


def score_deal(deal: dict):
    text = _text(deal)
    if _is_travel_deal(text):
        return _score_travel(text, deal)
    return _score_resell(text, deal)
