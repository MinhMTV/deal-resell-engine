"""Deal quality scoring: combines multiple signals into a single quality rating.

Score components (0-100):
- Profit Score (0-40): based on net profit margin
- Reliability Score (0-25): based on Geizhals match quality
- Market Position Score (0-20): how far below market the deal is
- Trend Score (-10 to +5): price trend bonus/penalty
- Risk Score (0-15): penalty for bundles, contracts, unverified sources
"""

from app.trend_predict import predict_trend


def calculate_deal_score(deal: dict) -> dict:
    """
    Calculate a quality score (0-100) for a deal based on multiple signals.

    Expected deal dict fields:
    - net_profit: float (from profit calculator)
    - net_roi_pct: float (ROI percentage)
    - diff: float (Geizhals min - deal price)
    - geizhals_min: float (Geizhals minimum price)
    - deal_price: float (what you pay)
    - is_contract: bool
    - is_bundle: bool
    - geizhals_link: str (has Geizhals product link = more reliable)
    - source: str (mydealz/preisjaeger)
    - normalized_model: str (for trend lookup)
    """

    scores = {}

    # 1. Profit Score (0-40 points)
    net_profit = deal.get("net_profit", 0) or 0
    roi_pct = deal.get("net_roi_pct", 0) or 0

    # Profit component: 0-25 points (up to 250€ profit = max)
    profit_points = min(25.0, max(0, net_profit * 0.1))

    # ROI component: 0-15 points (up to 100% ROI = max)
    roi_points = min(15.0, max(0, roi_pct * 0.15))

    scores["profit"] = round(profit_points + roi_points, 1)

    # 2. Reliability Score (0-25 points)
    reliability = 0.0

    # Geizhals link present = more reliable
    if deal.get("geizhals_link"):
        reliability += 10.0

    # Geizhals min exists and is reasonable
    geizhals_min = deal.get("geizhals_min")
    deal_price = deal.get("deal_price", 0)

    if geizhals_min and deal_price:
        ratio = geizhals_min / deal_price if deal_price > 0 else 0
        if 1.1 <= ratio <= 5.0:
            reliability += 10.0  # reasonable price ratio
        elif ratio > 5.0:
            reliability += 3.0  # suspiciously high ratio
        else:
            reliability += 5.0  # low ratio

    # Source reliability
    source = (deal.get("source") or "").lower()
    if source == "mydealz":
        reliability += 5.0  # most established
    elif source == "preisjaeger":
        reliability += 3.0

    scores["reliability"] = round(min(25.0, reliability), 1)

    # 3. Market Position Score (0-20 points)
    diff = deal.get("diff", 0) or 0

    if diff >= 500:
        market_points = 20.0  # massive deal
    elif diff >= 200:
        market_points = 15.0
    elif diff >= 100:
        market_points = 10.0
    elif diff >= 50:
        market_points = 7.0
    elif diff >= 20:
        market_points = 4.0
    else:
        market_points = 1.0

    scores["market_position"] = round(market_points, 1)

    # 4. Trend Score (-10 to +5 points)
    trend_points = 0.0
    model = deal.get("normalized_model")
    if model:
        trend = predict_trend(model, days=30)
        if trend and trend["confidence"] in ("high", "medium"):
            if trend["trend"] == "rising":
                trend_points = 5.0  # prices rising = good time to buy
            elif trend["trend"] == "dropping":
                trend_points = -10.0  # prices dropping = wait or risk
            # stable = 0 points (neutral)
        elif trend and trend["confidence"] == "low":
            if trend["trend"] == "rising":
                trend_points = 2.0
            elif trend["trend"] == "dropping":
                trend_points = -5.0

    scores["trend"] = round(trend_points, 1)

    # 5. Risk Penalty (0-15 points, subtracted from base)
    risk_penalty = 0.0

    if deal.get("is_contract"):
        risk_penalty += 5.0  # contract = more complex

    if deal.get("is_bundle"):
        risk_penalty += 5.0  # bundle = conditional pricing

    # Very high ratios are risky
    if geizhals_min and deal_price and geizhals_min / deal_price > 5:
        risk_penalty += 5.0

    scores["risk_penalty"] = round(min(15.0, risk_penalty), 1)

    # Total Score
    total = scores["profit"] + scores["reliability"] + scores["market_position"] + scores["trend"] - scores["risk_penalty"]
    scores["total"] = round(max(0, min(100, total)), 1)

    # Rating
    if scores["total"] >= 80:
        scores["rating"] = "🔥 EXZELLENT"
    elif scores["total"] >= 60:
        scores["rating"] = "✅ GUT"
    elif scores["total"] >= 40:
        scores["rating"] = "⚠️ OK"
    elif scores["total"] >= 20:
        scores["rating"] = "⚠️ RISIKO"
    else:
        scores["rating"] = "❌ SCHLECHT"

    return scores


def format_score_line(scores: dict) -> str:
    """Format score as a readable line."""
    trend_str = f" | Trend: {scores['trend']:+.1f}" if scores.get("trend") else ""
    return (
        f"{scores['rating']} | Score: {scores['total']}/100 | "
        f"Profit: {scores['profit']} | Reliability: {scores['reliability']} | "
        f"Market: {scores['market_position']}{trend_str} | Risk: -{scores['risk_penalty']}"
    )
