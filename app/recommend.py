"""Buy recommendation engine: analyzes price history + current deals to recommend what to buy.

Combines:
- Current deal price vs Geizhals
- Price history (is it near all-time low?)
- Net profit after fees
- Quality score
- Time sensitivity (how long has the deal been up?)
"""

from datetime import datetime, timezone
from app.price_history import get_price_stats
from app.profit import calculate_best_platform, format_profit_line


def score_recommendation(deal: dict) -> dict:
    """
    Score a deal for buy recommendation (0-100).

    Factors:
    - Deal price vs all-time Geizhals low (is this a good time to buy?)
    - Net profit potential
    - Price momentum (dropping or rising?)
    - Deal freshness
    """
    score = 0.0
    reasons = []

    model = deal.get("normalized_model")
    deal_price = deal.get("deal_price", 0)
    geizhals_min = deal.get("geizhals_min")

    # 1. Price vs all-time low (0-30 points)
    if model and geizhals_min:
        stats = get_price_stats(model, days=90)
        if stats:
            if stats["is_at_low"]:
                score += 30
                reasons.append("🔻 Allzeittief")
            elif stats["all_time_low"]:
                gap_to_low = geizhals_min - stats["all_time_low"]
                pct = gap_to_low / stats["all_time_low"] * 100 if stats["all_time_low"] > 0 else 100
                if pct < 5:
                    score += 25
                    reasons.append(f"📉 Fast Allzeittief ({pct:.0f}% drüber)")
                elif pct < 15:
                    score += 15
                    reasons.append(f"📊 {pct:.0f}% über Tiefstpreis")
                else:
                    score += 5

            # Momentum bonus: price dropping
            if stats.get("drop_from_high", 0) > 50:
                score += 10
                reasons.append(f"📉 Preis sinkt (-{stats['drop_from_high']}€)")

    # 2. Net profit potential (0-35 points)
    if geizhals_min and deal_price:
        best = calculate_best_platform(deal_price, geizhals_min)
        net = best["net_profit"]
        roi = best["roi_pct"]

        if net >= 200:
            score += 35
            reasons.append(f"💰 Hoher Gewinn: +{net}€")
        elif net >= 100:
            score += 25
            reasons.append(f"💰 Guter Gewinn: +{net}€")
        elif net >= 50:
            score += 15
            reasons.append(f"💰 OK Gewinn: +{net}€")
        elif net > 0:
            score += 5
            reasons.append(f"💰 Kleiner Gewinn: +{net}€")

        if roi >= 30:
            score += 5
            reasons.append(f"📈 ROI: {roi}%")

    # 3. Market position (0-20 points)
    diff = deal.get("diff", 0)
    if diff >= 500:
        score += 20
        reasons.append("🔥 Mega-Differenz")
    elif diff >= 200:
        score += 15
        reasons.append("✅ Große Differenz")
    elif diff >= 100:
        score += 10
        reasons.append("✅ Solide Differenz")
    elif diff >= 50:
        score += 5

    # 4. Risk penalties
    if deal.get("is_contract"):
        score -= 10
        reasons.append("⚠️ Vertrag (Risiko)")
    if deal.get("is_bundle"):
        score -= 10
        reasons.append("⚠️ Bundle (Risiko)")

    # Very high ratios are suspicious
    if geizhals_min and deal_price and geizhals_min / deal_price > 5:
        score -= 15
        reasons.append("🚨 Unrealistisches Verhältnis")

    score = max(0, min(100, score))

    # Recommendation
    if score >= 70:
        recommendation = "🟢 KAUFEN"
    elif score >= 50:
        recommendation = "🟡 IN BETRACHT ZIEHEN"
    elif score >= 30:
        recommendation = "🟠 ABWARTEN"
    else:
        recommendation = "🔴 ÜBERSPRINGEN"

    return {
        "score": round(score, 1),
        "recommendation": recommendation,
        "reasons": reasons,
    }


def format_recommendation(rec: dict) -> str:
    """Format recommendation as readable line."""
    reasons = " | ".join(rec["reasons"][:4])
    return f"{rec['recommendation']} (Score: {rec['score']}/100) — {reasons}"
