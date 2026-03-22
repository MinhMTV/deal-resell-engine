#!/usr/bin/env python3
"""Retry queue processor: re-check failed Geizhals matches from previous runs.

Usage:
  python scripts/retry_queue.py              # process queue, text output
  python scripts/retry_queue.py --out json   # JSON output
  python scripts/retry_queue.py --max-age 3  # drop entries older than 3 days
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.market_price import estimate_market_price_debug

QUEUE_PATH = PROJECT_ROOT / "state" / "retry_queue.json"
HITS_PATH = PROJECT_ROOT / "state" / "retry_hits.json"


def load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    try:
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_queue(rows: list[dict]):
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_hits() -> list[dict]:
    if not HITS_PATH.exists():
        return []
    try:
        return json.loads(HITS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_hits(hits: list[dict]):
    HITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HITS_PATH.write_text(json.dumps(hits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_queue(max_age_days: int = 7, min_diff: float = 15.0) -> dict:
    queue = load_queue()
    if not queue:
        return {"checked": 0, "hits": [], "remaining": 0, "expired": 0}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)

    remaining = []
    hits = []
    expired = 0
    checked = 0

    for entry in queue:
        # Expiry check
        added_at = entry.get("added_at")
        if added_at:
            try:
                added = datetime.fromisoformat(added_at)
                if added < cutoff:
                    expired += 1
                    continue
            except Exception:
                pass

        model = entry.get("normalized_model")
        if not model:
            continue

        checked += 1
        deal_input = {
            "normalized_model": model,
            "normalized_storage_gb": entry.get("normalized_storage_gb"),
        }
        debug = estimate_market_price_debug(deal_input, mode="geizhals")
        geizhals_min = debug.get("price")

        if geizhals_min is None:
            # Still no match — keep in queue with retry counter
            entry["retries"] = entry.get("retries", 0) + 1
            entry["last_attempt"] = now.isoformat()
            remaining.append(entry)
            continue

        deal_price = entry.get("price")
        if deal_price is None:
            remaining.append(entry)
            continue

        diff = round(float(geizhals_min) - float(deal_price), 2)
        if diff >= min_diff:
            best_attempt = next(
                (a for a in debug.get("attempts", []) if a.get("price") is not None), None
            )
            geizhals_link = None
            if best_attempt and best_attempt.get("inliers"):
                geizhals_link = best_attempt["inliers"][0].get("url")

            hit = {
                "source": entry.get("source"),
                "title": entry.get("title"),
                "deal_url": entry.get("url"),
                "deal_price": float(deal_price),
                "normalized_model": model,
                "normalized_storage_gb": entry.get("normalized_storage_gb"),
                "geizhals_min": float(geizhals_min),
                "geizhals_link": geizhals_link,
                "diff": diff,
                "found_at": now.isoformat(),
                "retries_before_hit": entry.get("retries", 0),
            }
            hits.append(hit)
        else:
            # Price exists but diff too small — remove from queue (no profit)
            pass

    save_queue(remaining)
    if hits:
        existing_hits = load_hits()
        existing_hits.extend(hits)
        save_hits(existing_hits)

    return {"checked": checked, "hits": hits, "remaining": len(remaining), "expired": expired}


def main():
    p = argparse.ArgumentParser(description="Retry queue processor")
    p.add_argument("--max-age", type=int, default=7, help="Drop entries older than N days")
    p.add_argument("--min-diff", type=float, default=15.0, help="Min Geizhals price diff in €")
    p.add_argument("--out", choices=["text", "json"], default="text")
    args = p.parse_args()

    result = process_queue(max_age_days=args.max_age, min_diff=args.min_diff)

    if args.out == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"Retry Queue: {result['checked']} checked | {len(result['hits'])} new hits | {result['remaining']} remaining | {result['expired']} expired")
    for i, h in enumerate(result["hits"], 1):
        print(
            f"{i}. +{h['diff']}€ [{h['source']}] {h['normalized_model']}\n"
            f"   deal: {h['deal_price']}€ -> {h['deal_url']}\n"
            f"   geizhals: {h['geizhals_min']}€ -> {h['geizhals_link']}\n"
            f"   (after {h['retries_before_hit']} retries)"
        )


if __name__ == "__main__":
    main()
