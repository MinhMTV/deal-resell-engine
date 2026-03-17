from app.config import KEYWORDS

def score_deal(deal: dict):
    title = (deal.get("title") or "").lower()
    votes = int(deal.get("votes") or 0)
    price = float(deal.get("price") or 0)

    keyword_hits = sum(1 for k in KEYWORDS if k in title)
    community = min(max(votes, 0), 300) / 3  # 0..100

    price_bucket = 0
    if 100 <= price <= 1200:
        price_bucket = 20
    elif 20 <= price < 100:
        price_bucket = 10

    score = min(100, keyword_hits * 15 + community * 0.5 + price_bucket)

    reasons = []
    if keyword_hits:
        reasons.append(f"keyword_hits={keyword_hits}")
    reasons.append(f"votes={votes}")
    reasons.append(f"price={price}")
    return round(score, 2), ", ".join(reasons)
