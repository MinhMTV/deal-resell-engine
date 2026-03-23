"""Deal Pipeline Tracker — lifecycle tracking for reseller deals.

Tracks each deal through stages:
  found → compared → notified → bought → sold → archived

Provides stats on conversion, profit potential, and pipeline health.
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.config import DB_PATH

TRACKER_SCHEMA = """
CREATE TABLE IF NOT EXISTS deal_pipeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  normalized_model TEXT,
  normalized_storage_gb INTEGER,
  deal_url TEXT,
  deal_price REAL,
  effective_price REAL,
  geizhals_min REAL,
  geizhals_link TEXT,
  diff REAL,
  net_profit REAL,
  net_roi_pct REAL,
  net_platform TEXT,
  is_contract INTEGER DEFAULT 0,
  is_bundle INTEGER DEFAULT 0,
  stage TEXT NOT NULL DEFAULT 'found',
  found_at TEXT NOT NULL,
  compared_at TEXT,
  notified_at TEXT,
  bought_at TEXT,
  sold_at TEXT,
  archived_at TEXT,
  sold_price REAL,
  notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect_tracker(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open DB and ensure tracker table exists."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(TRACKER_SCHEMA)
    conn.commit()
    return conn


def mark_found(conn: sqlite3.Connection, hit: dict) -> bool:
    """Record a newly found deal. Returns True if new, False if already tracked."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            """INSERT INTO deal_pipeline (
                alert_key, source, normalized_model, normalized_storage_gb,
                deal_url, deal_price, effective_price, geizhals_min, geizhals_link,
                diff, net_profit, net_roi_pct, net_platform,
                is_contract, is_bundle, stage, found_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'found', ?)""",
            (
                hit.get("alert_key", ""),
                hit.get("source", ""),
                hit.get("normalized_model"),
                hit.get("normalized_storage_gb"),
                hit.get("deal_url") or hit.get("url"),
                hit.get("deal_price") or hit.get("price"),
                hit.get("effective_price"),
                hit.get("geizhals_min"),
                hit.get("geizhals_link"),
                hit.get("diff"),
                hit.get("net_profit"),
                hit.get("net_roi_pct"),
                hit.get("net_platform"),
                1 if hit.get("is_contract") else 0,
                1 if hit.get("is_bundle") else 0,
                now,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def update_stage(conn: sqlite3.Connection, alert_key: str, stage: str, **extra) -> bool:
    """Advance a deal to a new stage. Returns True if updated."""
    valid_stages = ("found", "compared", "notified", "bought", "sold", "archived")
    if stage not in valid_stages:
        raise ValueError(f"Invalid stage: {stage}. Must be one of {valid_stages}")

    now = datetime.now(timezone.utc).isoformat()
    stage_col = f"{stage}_at"

    sets = ["stage = ?", "updated_at = ?", f"{stage_col} = ?"]
    params = [stage, now, now]

    if "sold_price" in extra:
        sets.append("sold_price = ?")
        params.append(extra["sold_price"])
    if "notes" in extra:
        sets.append("notes = ?")
        params.append(extra["notes"])

    params.append(alert_key)
    cur = conn.execute(
        f"UPDATE deal_pipeline SET {', '.join(sets)} WHERE alert_key = ?",
        params,
    )
    conn.commit()
    return cur.rowcount > 0


def get_deal(conn: sqlite3.Connection, alert_key: str) -> dict | None:
    """Get a single deal by alert_key."""
    cur = conn.execute(
        "SELECT * FROM deal_pipeline WHERE alert_key = ?", (alert_key,)
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def list_deals(
    conn: sqlite3.Connection,
    stage: str | None = None,
    days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """List deals with optional stage filter."""
    query = "SELECT * FROM deal_pipeline WHERE datetime(found_at) >= datetime('now', ?)"
    params = [f"-{int(days)} days"]

    if stage:
        query += " AND stage = ?"
        params.append(stage)

    query += " ORDER BY found_at DESC LIMIT ?"
    params.append(int(limit))

    cur = conn.execute(query, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_pipeline_stats(conn: sqlite3.Connection, days: int = 30) -> dict:
    """Aggregate pipeline statistics."""
    cutoff = f"-{int(days)} days"

    # Stage counts
    cur = conn.execute(
        """SELECT stage, COUNT(*), AVG(diff), AVG(net_profit), AVG(net_roi_pct)
           FROM deal_pipeline
           WHERE datetime(found_at) >= datetime('now', ?)
           GROUP BY stage""",
        (cutoff,),
    )
    stages = {}
    for row in cur.fetchall():
        stage, count, avg_diff, avg_profit, avg_roi = row
        stages[stage] = {
            "count": count,
            "avg_diff": round(avg_diff, 2) if avg_diff else None,
            "avg_profit": round(avg_profit, 2) if avg_profit else None,
            "avg_roi_pct": round(avg_roi, 2) if avg_roi else None,
        }

    # Total found
    total_found = sum(s["count"] for s in stages.values())

    # Best deals (by net_profit)
    cur = conn.execute(
        """SELECT alert_key, normalized_model, deal_price, geizhals_min,
                  diff, net_profit, net_roi_pct, stage, found_at
           FROM deal_pipeline
           WHERE datetime(found_at) >= datetime('now', ?)
             AND net_profit IS NOT NULL
           ORDER BY net_profit DESC
           LIMIT 5""",
        (cutoff,),
    )
    cols = [d[0] for d in cur.description]
    best_deals = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Deals per day
    cur = conn.execute(
        """SELECT DATE(found_at) as day, COUNT(*) as cnt
           FROM deal_pipeline
           WHERE datetime(found_at) >= datetime('now', ?)
           GROUP BY day
           ORDER BY day DESC
           LIMIT 7""",
        (cutoff,),
    )
    daily = {row[0]: row[1] for row in cur.fetchall()}

    # Conversion rates
    compared = stages.get("compared", {}).get("count", 0)
    notified = stages.get("notified", {}).get("count", 0)
    bought = stages.get("bought", {}).get("count", 0)
    sold = stages.get("sold", {}).get("count", 0)

    return {
        "period_days": days,
        "total_found": total_found,
        "stages": stages,
        "conversion": {
            "found_to_notified_pct": round(notified / total_found * 100, 1) if total_found else 0,
            "notified_to_bought_pct": round(bought / notified * 100, 1) if notified else 0,
            "bought_to_sold_pct": round(sold / bought * 100, 1) if bought else 0,
        },
        "best_deals": best_deals,
        "daily_volume": daily,
    }


def format_pipeline_stats(stats: dict) -> str:
    """Format pipeline stats as human-readable text."""
    lines = []
    lines.append(f"📊 **Deal-Pipeline Stats** ({stats['period_days']} Tage)\n")
    lines.append(f"Gefunden: **{stats['total_found']}** Deals\n")

    stage_labels = {
        "found": "🔍 Gefunden",
        "compared": "⚖️ Verglichen",
        "notified": "📲 Benachrichtigt",
        "bought": "🛒 Gekauft",
        "sold": "💰 Verkauft",
        "archived": "📦 Archiviert",
    }

    lines.append("**Stages:**")
    for stage, label in stage_labels.items():
        s = stats["stages"].get(stage)
        if s:
            profit_info = f" (Ø {s['avg_profit']}€ profit)" if s.get("avg_profit") else ""
            lines.append(f"  {label}: {s['count']}{profit_info}")

    conv = stats["conversion"]
    lines.append(f"\n**Conversion:**")
    lines.append(f"  Found → Notified: {conv['found_to_notified_pct']}%")
    lines.append(f"  Notified → Bought: {conv['notified_to_bought_pct']}%")
    lines.append(f"  Bought → Sold: {conv['bought_to_sold_pct']}%")

    if stats["best_deals"]:
        lines.append(f"\n**Top 3 Deals (Netto-Profit):**")
        for i, d in enumerate(stats["best_deals"][:3], 1):
            model = (d.get("normalized_model") or "?").title()
            profit = d.get("net_profit", 0)
            roi = d.get("net_roi_pct", 0)
            stage = stage_labels.get(d.get("stage", ""), d.get("stage", ""))
            lines.append(f"  {i}. {model} — +{profit}€ (+{roi}%) [{stage}]")

    if stats["daily_volume"]:
        lines.append(f"\n**Letzte Tage:**")
        for day, cnt in sorted(stats["daily_volume"].items(), reverse=True)[:5]:
            lines.append(f"  {day}: {cnt} Deals")

    return "\n".join(lines)


def format_deal_detail(deal: dict) -> str:
    """Format a single deal as human-readable text."""
    stage_labels = {
        "found": "🔍 Gefunden",
        "compared": "⚖️ Verglichen",
        "notified": "📲 Benachrichtigt",
        "bought": "🛒 Gekauft",
        "sold": "💰 Verkauft",
        "archived": "📦 Archiviert",
    }
    model = (deal.get("normalized_model") or "?").title()
    storage = f" {deal['normalized_storage_gb']}GB" if deal.get("normalized_storage_gb") else ""
    stage = stage_labels.get(deal.get("stage", ""), deal.get("stage", ""))
    price = deal.get("deal_price", "?")
    diff = deal.get("diff")
    profit = deal.get("net_profit")
    url = deal.get("deal_url", "")

    lines = [
        f"{'📋' if deal.get('is_contract') else '📦'} {model}{storage} — {price}€",
        f"   Stage: {stage}",
        f"   {url}",
    ]
    if diff is not None:
        lines.append(f"   Diff: +{diff}€")
    if profit is not None:
        lines.append(f"   Netto-Profit: +{profit}€ ({deal.get('net_roi_pct', 0)}% via {deal.get('net_platform', '?')})")
    if deal.get("geizhals_link"):
        lines.append(f"   Geizhals: {deal['geizhals_link']}")
    if deal.get("notes"):
        lines.append(f"   Notiz: {deal['notes']}")
    if deal.get("sold_price"):
        lines.append(f"   Verkauft für: {deal['sold_price']}€")

    found = deal.get("found_at", "")[:10]
    lines.append(f"   Gefunden: {found}")

    return "\n".join(lines)
