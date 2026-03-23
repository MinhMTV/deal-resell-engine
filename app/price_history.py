"""Price history tracking for Geizhals prices over time.

Tracks price snapshots per model and detects:
- Price drops
- All-time lows
- 7/30 day trends
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parents[1] / "state" / "price_history.json"


def _load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_history(data: dict):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def log_price(model: str, price: float, source: str = "geizhals", url: str | None = None):
    """Log a price snapshot for a model."""
    history = _load_history()
    key = model.lower().strip()

    if key not in history:
        history[key] = {"snapshots": [], "all_time_low": None, "last_price": None}

    entry = {
        "price": round(price, 2),
        "source": source,
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    history[key]["snapshots"].append(entry)
    history[key]["last_price"] = round(price, 2)
    history[key]["last_updated"] = entry["timestamp"]

    # Update all-time low
    if history[key]["all_time_low"] is None or price < history[key]["all_time_low"]:
        history[key]["all_time_low"] = round(price, 2)
        history[key]["all_time_low_at"] = entry["timestamp"]

    # Keep last 90 days of snapshots
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    history[key]["snapshots"] = [
        s for s in history[key]["snapshots"] if s.get("timestamp", "") >= cutoff
    ]

    _save_history(history)
    return history[key]


def get_price_stats(model: str, days: int = 30) -> dict | None:
    """Get price statistics for a model over the last N days."""
    history = _load_history()
    key = model.lower().strip()

    if key not in history:
        return None

    data = history[key]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    recent = [s["price"] for s in data["snapshots"] if s.get("timestamp", "") >= cutoff]

    if not recent:
        return None

    return {
        "model": model,
        "current": data["last_price"],
        "all_time_low": data["all_time_low"],
        "all_time_low_at": data.get("all_time_low_at"),
        "period_low": min(recent),
        "period_high": max(recent),
        "period_avg": round(sum(recent) / len(recent), 2),
        "samples": len(recent),
        "days": days,
        "is_at_low": data["last_price"] == data["all_time_low"],
        "drop_from_high": round(max(recent) - data["last_price"], 2) if len(recent) > 1 else 0,
    }


def get_all_tracked() -> list[dict]:
    """Get summary of all tracked models."""
    history = _load_history()
    results = []
    for model, data in history.items():
        stats = get_price_stats(model, days=7)
        if stats:
            results.append(stats)
    results.sort(key=lambda x: x.get("drop_from_high", 0), reverse=True)
    return results


def format_price_trend(stats: dict) -> str:
    """Format price stats as a readable trend line."""
    if not stats:
        return ""

    parts = [f"📊 {stats['model'].title()}"]
    parts.append(f"Jetzt: {stats['current']}€")

    if stats["is_at_low"]:
        parts.append("🔻 Allzeittief!")
    else:
        parts.append(f"Tief: {stats['period_low']}€ ({stats['days']}d)")

    if stats["drop_from_high"] > 0:
        parts.append(f"📉 -{stats['drop_from_high']}€ vom Hoch")

    parts.append(f"Ø: {stats['period_avg']}€ ({stats['samples']} Messungen)")

    return " | ".join(parts)
