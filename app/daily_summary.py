"""Daily stats summary for the deal engine.

Provides a comprehensive overview of:
- Trend predictions (linear regression)
- Price movements
- Pipeline stats (deal lifecycle)
- System health
"""

from app.price_history import get_all_tracked, get_price_stats
from app.trend_predict import get_all_trends, format_trends_summary
from app.deal_tracker import connect_tracker, get_pipeline_stats


def generate_daily_summary(hits: list[dict] | None = None, include_pipeline: bool = True) -> str:
    """Generate a full daily summary string."""
    lines = []
    lines.append("📊 **Deal-Engine Tagesbericht**\n")

    # Trend predictions
    trends = get_all_trends(days=30)
    if trends:
        lines.append(format_trends_summary(trends))
        lines.append("")

    # Pipeline stats
    if include_pipeline:
        conn = connect_tracker()
        stats = get_pipeline_stats(conn, days=7)
        total = stats["total_found"]
        if total > 0:
            lines.append("**📦 Deal-Pipeline (7 Tage):**")
            stage_labels = {
                "found": "🔍 Gefunden",
                "notified": "📲 Benachrichtigt",
                "bought": "🛒 Gekauft",
                "sold": "💰 Verkauft",
            }
            for stage, label in stage_labels.items():
                s = stats["stages"].get(stage)
                if s:
                    lines.append(f"  {label}: {s['count']}")

            conv = stats["conversion"]
            lines.append(f"  Conversion: {conv['found_to_notified_pct']}% → Benachrichtigt")

            if stats["best_deals"]:
                lines.append(f"  Top Deal: {stats['best_deals'][0]['normalized_model'].title()} (+{stats['best_deals'][0]['net_profit']}€)")
            lines.append("")
        conn.close()

    # Price movements
    tracked = get_all_tracked()
    if tracked:
        lines.append("**📈 Preisbewegungen:**")
        for s in tracked[:5]:
            direction = "📉" if s.get("drop_from_high", 0) > 0 else "📊"
            low_marker = "🔻 Allzeittief!" if s["is_at_low"] else ""
            lines.append(
                f"  {direction} {s['model'].title()}: {s['current']}€ "
                f"(Tief: {s['period_low']}€, Ø: {s['period_avg']}€) {low_marker}"
            )
        lines.append("")

    # Best deals from last run
    if hits:
        lines.append("**🏆 Top Deals:**")
        for i, h in enumerate(hits[:5], 1):
            emoji = "📱" if "galaxy" in h.get("normalized_model", "").lower() or "iphone" in h.get("normalized_model", "").lower() else "🏷️"
            model = h.get("normalized_model", "unknown").title()
            diff = h.get("diff", 0)
            profit = h.get("net_profit", 0)
            rec = h.get("recommendation", {}).get("recommendation", "")
            lines.append(f"  {i}. {emoji} {model} — +{diff}€ Diff, +{profit}€ netto {rec}")
        lines.append("")

    # System health
    lines.append(f"**📊 System:** {len(tracked)} Modelle getrackt | {len(hits) if hits else 0} Deals letzter Run")

    return "\n".join(lines)


def generate_daily_summary_json(hits: list[dict] | None = None) -> dict:
    """Generate daily summary as structured data."""
    trends = get_all_trends(days=30)
    tracked = get_all_tracked()

    conn = connect_tracker()
    pipeline = get_pipeline_stats(conn, days=7)
    conn.close()

    return {
        "trends": trends,
        "price_movements": tracked[:5],
        "pipeline": pipeline,
        "top_deals": (hits or [])[:5],
        "system_health": {
            "tracked_models": len(tracked),
            "last_run_deals": len(hits) if hits else 0,
        },
    }
