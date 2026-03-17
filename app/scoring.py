from app.config import KEYWORDS, TRAVEL_AIRPORTS


def score_deal(deal: dict):
    title = (deal.get("title") or "").lower()
    votes = int(deal.get("votes") or 0)
    price = float(deal.get("price") or 0)

    keyword_hits = sum(1 for k in KEYWORDS if k in title)
    airport_hits = sum(1 for a in TRAVEL_AIRPORTS if a in title)
    community = min(max(votes, 0), 300) / 3  # 0..100

    price_bucket = 0
    if 100 <= price <= 1200:
        price_bucket = 20
    elif 20 <= price < 100:
        price_bucket = 10

    travel_bonus = 0
    if any(x in title for x in ["flug", "reise", "urlaub"]):
        travel_bonus += 8
    if airport_hits >= 1:
        travel_bonus += 7

    score = min(100, keyword_hits * 15 + community * 0.5 + price_bucket + travel_bonus)

    reasons = []
    if keyword_hits:
        reasons.append(f"keyword_hits={keyword_hits}")
    if airport_hits:
        reasons.append(f"airport_hits={airport_hits}")
    reasons.append(f"votes={votes}")
    reasons.append(f"price={price}")
    return round(score, 2), ", ".join(reasons)
