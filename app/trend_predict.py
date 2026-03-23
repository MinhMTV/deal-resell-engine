"""Price Trend Predictor — linear regression on Geizhals price history.

Predicts price direction and future price points to help score deals:
- Trend direction: dropping ↘, stable →, rising ↗
- Predicted price in 7/14 days
- Confidence based on sample count and fit quality
"""

import math
from datetime import datetime, timezone, timedelta
from app.price_history import _load_history


def predict_trend(model: str, days: int = 30, predict_ahead: int = 7) -> dict | None:
    """Predict price trend using simple linear regression on recent snapshots.

    Returns:
        {
            "model": str,
            "current_price": float,
            "trend": "dropping" | "stable" | "rising",
            "slope_per_day": float,  # € change per day
            "predicted_price_7d": float,
            "predicted_price_14d": float,
            "r_squared": float,  # 0-1 fit quality
            "confidence": "high" | "medium" | "low",
            "samples": int,
            "days_analyzed": int,
            "recommendation": str,
        }
    """
    history = _load_history()
    key = model.lower().strip()

    if key not in history:
        return None

    data = history[key]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Get snapshots with timestamps
    snapshots = [
        s for s in data["snapshots"]
        if s.get("timestamp", "") >= cutoff and s.get("price") is not None
    ]

    if len(snapshots) < 3:
        return None

    # Convert timestamps to day offsets from first snapshot
    first_ts = datetime.fromisoformat(snapshots[0]["timestamp"])
    points = []
    for s in snapshots:
        ts = datetime.fromisoformat(s["timestamp"])
        day_offset = (ts - first_ts).total_seconds() / 86400.0
        points.append((day_offset, s["price"]))

    n = len(points)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xx = sum(p[0] ** 2 for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)

    denom = n * sum_xx - sum_x ** 2
    if abs(denom) < 1e-10:
        # All points at same x — can't regress
        return _flat_result(model, data, snapshots, days)

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R² calculation
    mean_y = sum_y / n
    ss_tot = sum((p[1] - mean_y) ** 2 for p in points)
    ss_res = sum((p[1] - (slope * p[0] + intercept)) ** 2 for p in points)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))

    # Current price and predictions
    current_price = data["last_price"]
    last_day = points[-1][0]
    pred_7d = slope * (last_day + predict_ahead) + intercept
    pred_14d = slope * (last_day + 2 * predict_ahead) + intercept

    # Slope per day in €
    slope_per_day = round(slope, 4)

    # Trend classification
    slope_threshold = 0.50  # €/day threshold for "stable"
    if slope < -slope_threshold:
        trend = "dropping"
    elif slope > slope_threshold:
        trend = "rising"
    else:
        trend = "stable"

    # Confidence based on samples and R²
    if n >= 10 and r_squared >= 0.5:
        confidence = "high"
    elif n >= 5 and r_squared >= 0.2:
        confidence = "medium"
    else:
        confidence = "low"

    # Recommendation
    if trend == "dropping" and confidence in ("high", "medium"):
        recommendation = "⏳ Warten — Preis fällt. In 7d voraussichtlich {:.0f}€".format(max(0, pred_7d))
    elif trend == "rising" and confidence in ("high", "medium"):
        recommendation = "🚀 Jetzt kaufen — Preis steigt!"
    elif trend == "stable":
        recommendation = "📊 Preis stabil — zuschlagen wenn Diff gut ist"
    else:
        recommendation = "🔮 Trend unklar — mehr Daten nötig"

    return {
        "model": model,
        "current_price": current_price,
        "trend": trend,
        "slope_per_day": slope_per_day,
        "predicted_price_7d": round(max(0, pred_7d), 2),
        "predicted_price_14d": round(max(0, pred_14d), 2),
        "r_squared": round(r_squared, 3),
        "confidence": confidence,
        "samples": n,
        "days_analyzed": days,
        "recommendation": recommendation,
    }


def _flat_result(model: str, data: dict, snapshots: list, days: int) -> dict:
    """Return flat trend result when regression isn't possible."""
    current = data["last_price"]
    return {
        "model": model,
        "current_price": current,
        "trend": "stable",
        "slope_per_day": 0.0,
        "predicted_price_7d": current,
        "predicted_price_14d": current,
        "r_squared": 0.0,
        "confidence": "low",
        "samples": len(snapshots),
        "days_analyzed": days,
        "recommendation": "📊 Preis stabil — zuschlagen wenn Diff gut ist",
    }


def get_all_trends(days: int = 30, predict_ahead: int = 7) -> list[dict]:
    """Get trend predictions for all tracked models."""
    history = _load_history()
    results = []
    for model in history:
        pred = predict_trend(model, days=days, predict_ahead=predict_ahead)
        if pred:
            results.append(pred)
    # Sort: dropping first (best for buyers), then stable, then rising
    order = {"dropping": 0, "stable": 1, "rising": 2}
    results.sort(key=lambda x: (order.get(x["trend"], 3), x["slope_per_day"]))
    return results


def format_trend_prediction(pred: dict) -> str:
    """Format trend prediction as human-readable text."""
    if not pred:
        return ""

    trend_emoji = {"dropping": "📉", "stable": "📊", "rising": "📈"}
    emoji = trend_emoji.get(pred["trend"], "❓")
    conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}

    parts = [
        f"{emoji} **{pred['model'].title()}** — {pred['trend'].upper()}",
        f"Aktuell: {pred['current_price']}€",
        f"Trend: {pred['slope_per_day']:+.2f}€/Tag",
        f"7d Prognose: {pred['predicted_price_7d']}€",
        f"14d Prognose: {pred['predicted_price_14d']}€",
        f"Konfidenz: {conf_emoji.get(pred['confidence'], '❓')} {pred['confidence']} (R²={pred['r_squared']}, {pred['samples']} Messungen)",
        f"→ {pred['recommendation']}",
    ]
    return "\n".join(parts)


def format_trends_summary(trends: list[dict]) -> str:
    """Format all trends as a compact summary."""
    if not trends:
        return "Keine Trend-Daten verfügbar."

    lines = ["📈 **Preis-Trend-Prognosen**\n"]

    dropping = [t for t in trends if t["trend"] == "dropping"]
    stable = [t for t in trends if t["trend"] == "stable"]
    rising = [t for t in trends if t["trend"] == "rising"]

    if dropping:
        lines.append("**📉 Fallend (gut zum Warten):**")
        for t in dropping:
            conf = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(t["confidence"], "")
            lines.append(f"  {conf} {t['model'].title()}: {t['current_price']}€ → ~{t['predicted_price_7d']}€ in 7d ({t['slope_per_day']:+.1f}€/d)")
        lines.append("")

    if stable:
        lines.append("**📊 Stabil:**")
        for t in stable:
            lines.append(f"  • {t['model'].title()}: {t['current_price']}€ (gleichbleibend)")
        lines.append("")

    if rising:
        lines.append("**📈 Steigend (bald zuschlagen!):**")
        for t in rising:
            conf = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(t["confidence"], "")
            lines.append(f"  {conf} {t['model'].title()}: {t['current_price']}€ → ~{t['predicted_price_7d']}€ in 7d ({t['slope_per_day']:+.1f}€/d)")
        lines.append("")

    return "\n".join(lines)
