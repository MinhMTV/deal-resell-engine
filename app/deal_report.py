"""Deal Report Generator — daily and weekly deal reports with top profits."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.deal_tracker import connect_tracker, get_pipeline_stats, list_deals, format_deal_detail
from app.trend_predict import get_all_trends, format_trends_summary


def generate_deal_report(days: int = 1, top_n: int = 10) -> str:
    """Generate a deal report for the specified period.

    Includes:
      - Pipeline stats summary
      - Top N deals by net profit
      - Trend predictions for tracked models
      - Expiry status overview
    """
    conn = connect_tracker()
    stats = get_pipeline_stats(conn, days=days)
    deals = list_deals(conn, days=days, limit=100)
    conn.close()

    lines = []
    period_label = "Heute" if days == 1 else f"Letzte {days} Tage"
    lines.append(f"📊 **Deal Report — {period_label}**")
    lines.append(f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    # Pipeline stats
    total = stats["total_found"]
    if total == 0:
        lines.append("Keine Deals in diesem Zeitraum.")
        return "\n".join(lines)

    lines.append(f"**Gefunden:** {total} Deals\n")

    # Stage breakdown
    stage_labels = {
        "found": "🔍 Gefunden",
        "notified": "📲 Benachrichtigt",
        "bought": "🛒 Gekauft",
        "sold": "💰 Verkauft",
        "archived": "📦 Archiviert",
    }
    for stage, label in stage_labels.items():
        s = stats["stages"].get(stage)
        if s:
            profit_info = f" (Ø {s['avg_profit']}€)" if s.get("avg_profit") else ""
            lines.append(f"  {label}: {s['count']}{profit_info}")

    # Conversion
    conv = stats["conversion"]
    lines.append(f"\n**Conversion:** Found→Notified: {conv['found_to_notified_pct']}%")

    # Top deals by profit
    profitable = [d for d in deals if d.get("net_profit") and d["net_profit"] > 0]
    profitable.sort(key=lambda x: x.get("net_profit", 0), reverse=True)

    if profitable:
        lines.append(f"\n**🏆 Top {min(top_n, len(profitable))} Deals nach Netto-Profit:**")
        for i, d in enumerate(profitable[:top_n], 1):
            model = (d.get("normalized_model") or "?").title()
            profit = d.get("net_profit", 0)
            roi = d.get("net_roi_pct", 0)
            price = d.get("deal_price", "?")
            stage = d.get("stage", "?")
            url = d.get("deal_url", "")[:60]
            lines.append(f"  {i}. {model} — {price}€ → +{profit}€ (+{roi}%) [{stage}]")
            lines.append(f"     {url}")

    # By source
    sources = {}
    for d in deals:
        src = d.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    if sources:
        lines.append(f"\n**Nach Quelle:**")
        for src, cnt in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {src}: {cnt} Deals")

    # Trend predictions
    trends = get_all_trends(days=30)
    if trends:
        lines.append(f"\n{format_trends_summary(trends)}")

    return "\n".join(lines)


def generate_deal_report_json(days: int = 1) -> dict:
    """Generate deal report as structured data."""
    conn = connect_tracker()
    stats = get_pipeline_stats(conn, days=days)
    deals = list_deals(conn, days=days, limit=100)
    conn.close()

    profitable = [d for d in deals if d.get("net_profit") and d["net_profit"] > 0]
    profitable.sort(key=lambda x: x.get("net_profit", 0), reverse=True)

    trends = get_all_trends(days=30)

    return {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_stats": stats,
        "top_deals": profitable[:10],
        "trends": trends,
        "total": stats["total_found"],
    }
