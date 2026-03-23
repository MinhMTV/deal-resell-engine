"""Daily stats summary for the deal engine.

Provides a quick overview of:
- Best current deals
- Price movements
- System health
"""

from app.price_history import get_all_tracked, get_price_stats


def generate_daily_summary(hits: list[dict] | None = None) -> str:
    """Generate a daily summary string."""
    lines = []
    lines.append("📊 **Deal-Engine Tagesbericht**\n")

    # Price movements
    tracked = get_all_tracked()
    if tracked:
        lines.append("**Preisbewegungen:**")
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
        lines.append("**Top Deals:**")
        for i, h in enumerate(hits[:3], 1):
            emoji = "📱" if "galaxy" in h.get("normalized_model", "").lower() or "iphone" in h.get("normalized_model", "").lower() else "🏷️"
            model = h.get("normalized_model", "unknown").title()
            diff = h.get("diff", 0)
            profit = h.get("net_profit", 0)
            rec = h.get("recommendation", {}).get("recommendation", "")
            lines.append(f"  {i}. {emoji} {model} — +{diff}€ Diff, +{profit}€ netto {rec}")
        lines.append("")

    # System health
    lines.append(f"**Tracked Models:** {len(tracked)}")
    lines.append(f"**Deals gefundet:** {len(hits) if hits else 0}")

    return "\n".join(lines)
