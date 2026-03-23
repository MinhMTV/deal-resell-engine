#!/usr/bin/env python3
"""
Deal Live Poll: scrapes mydealz + preisjaeger, compares to Geizhals,
filters out already-seen deals, outputs new hits in alert format.

State file: state/sent_deals.json (list of seen alert_keys)
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.intake import fetch_live_source, detect_contract_deal, detect_bundle_deal
from app.normalize import normalize_product
from app.market_price import estimate_market_price_debug
from app.profit import calculate_best_platform, format_profit_line
from app.price_history import log_price
from app.deal_tracker import connect_tracker, mark_found, update_stage
from app.trend_predict import predict_trend

SENT_PATH = PROJECT_ROOT / "state" / "sent_deals.json"


def _alert_key(source: str, model: str | None, url: str) -> str:
    m = model or "unknown"
    h = hashlib.sha1((url or "").encode()).hexdigest()[:10]
    return f"{source}:{m}:{h}"


def load_sent() -> set:
    if not SENT_PATH.exists():
        return set()
    try:
        return set(json.loads(SENT_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_sent(keys: set):
    SENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep last 500 keys to prevent unbounded growth
    key_list = sorted(keys)[-500:]
    SENT_PATH.write_text(json.dumps(key_list, ensure_ascii=False) + "\n", encoding="utf-8")


def run_poll(max_pages: int = 15, max_checks: int = 60, min_diff: float = 15.0) -> dict:
    sent = load_sent()
    now = datetime.now(timezone.utc)
    tracker_conn = connect_tracker()

    all_deals = []
    for src in ["mydealz", "preisjaeger"]:
        rows, err = fetch_live_source(src, max_pages=max_pages)
        if err:
            print(f"WARN: {err}", file=sys.stderr)
        all_deals.extend(rows)

    new_hits = []
    retry_queue = []
    checked = 0
    skipped_seen = 0

    for d in all_deals:
        if checked >= max_checks:
            break
        price = d.get("price")
        if price is None:
            continue

        d = detect_contract_deal(d)
        d = detect_bundle_deal(d)
        is_contract = d.get("is_contract", False)
        contract_total = d.get("contract_total")
        if is_contract and contract_total is not None:
            effective_price = float(contract_total)
        else:
            effective_price = float(price)
            is_contract = False

        normalized = normalize_product(d.get("title", ""))
        model = normalized.get("normalized_model")
        if not model:
            continue

        key = _alert_key(d.get("source", ""), model, d.get("url", ""))
        if key in sent:
            skipped_seen += 1
            continue

        checked += 1
        deal_input = {
            "normalized_model": model,
            "normalized_storage_gb": normalized.get("normalized_storage_gb"),
        }
        debug = estimate_market_price_debug(deal_input, mode="geizhals")
        geizhals_min = debug.get("price")

        best_attempt = next(
            (a for a in debug.get("attempts", []) if a.get("price") is not None), None
        )
        geizhals_link = None
        if best_attempt and best_attempt.get("inliers"):
            geizhals_link = best_attempt["inliers"][0].get("url")
        elif best_attempt and best_attempt.get("url"):
            geizhals_link = best_attempt["url"]

        if geizhals_min is None:
            continue

        # Log price to history
        log_price(model, float(geizhals_min), source="geizhals", url=geizhals_link)

        diff = round(float(geizhals_min) - effective_price, 2)
        if diff < min_diff:
            continue

        best_profit = calculate_best_platform(effective_price, float(geizhals_min))

        hit = {
            "alert_key": key,
            "source": d.get("source"),
            "title": d.get("title"),
            "deal_url": d.get("url"),
            "deal_price": float(price),
            "effective_price": effective_price,
            "is_contract": is_contract,
            "is_bundle": d.get("is_bundle", False),
            "bundle_reason": d.get("bundle_reason"),
            "contract_monthly": d.get("contract_monthly"),
            "contract_months": d.get("contract_months"),
            "contract_upfront": d.get("contract_upfront"),
            "contract_total": d.get("contract_total"),
            "normalized_model": model,
            "normalized_storage_gb": normalized.get("normalized_storage_gb"),
            "geizhals_min": float(geizhals_min),
            "geizhals_link": geizhals_link,
            "diff": diff,
            "net_profit": best_profit["net_profit"],
            "net_roi_pct": best_profit["roi_pct"],
            "net_platform": best_profit["platform"],
            "profit_detail": format_profit_line(best_profit),
            "found_at": now.isoformat(),
        }
        new_hits.append(hit)
        sent.add(key)

        # Track in deal pipeline: found → notified (since it passed all filters)
        mark_found(tracker_conn, hit)
        update_stage(tracker_conn, key, "notified")

    tracker_conn.close()

    # Save updated sent state
    save_sent(sent)

    new_hits.sort(key=lambda x: x["diff"], reverse=True)

    return {
        "timestamp": now.isoformat(),
        "total_deals": len(all_deals),
        "checked": checked,
        "skipped_seen": skipped_seen,
        "new_hits": new_hits,
    }


def _emoji_for_model(model: str) -> str:
    m = (model or "").lower()
    if any(k in m for k in ["iphone", "galaxy s", "pixel", "oneplus"]):
        return "📱"
    if any(k in m for k in ["ipad", "galaxy tab", "oneplus pad"]):
        return "📟"
    if any(k in m for k in ["macbook", "thinkpad", "surface", "xps"]):
        return "💻"
    if any(k in m for k in ["switch", "playstation", "ps5", "xbox", "steam deck", "rog ally"]):
        return "🎮"
    if any(k in m for k in ["airpods", "galaxy buds", "watch"]):
        return "🎧"
    if any(k in m for k in ["airtag"]):
        return "📍"
    return "🏷️"


def print_alert(hits: list[dict]):
    if not hits:
        print("HEARTBEAT_OK")
        return

    direct = [h for h in hits if not h.get("is_contract")]
    contract = [h for h in hits if h.get("is_contract")]

    print(f"🔥 {len(hits)} neue Deal-Treffer:\n")

    if direct:
        for i, h in enumerate(direct, 1):
            emoji = _emoji_for_model(h.get("normalized_model", ""))
            storage = f" {h['normalized_storage_gb']}GB" if h.get("normalized_storage_gb") else ""
            diff_sign = "+" if h["diff"] > 0 else ""
            bundle_warn = f" ⚠️ Bundle ({h['bundle_reason']})" if h.get("is_bundle") else ""

            print(f"{i}. {emoji} {h['normalized_model'].title()}{storage} — {h['deal_price']}€ [{h['source']}]{bundle_warn}")
            print(f"   {h['deal_url']}")
            print(f"   🏷️ Geizhals: {h['geizhals_min']}€ → Diff: {diff_sign}{h['diff']}€")
            if h.get("geizhals_link"):
                print(f"   🔗 {h['geizhals_link']}")
            if h.get("profit_detail"):
                print(f"   💰 {h['profit_detail']}")

            # Trend prediction
            trend = predict_trend(h.get("normalized_model", ""), days=30)
            if trend:
                trend_emoji = {"dropping": "📉", "stable": "📊", "rising": "📈"}.get(trend["trend"], "❓")
                print(f"   {trend_emoji} Trend: {trend['trend']} ({trend['slope_per_day']:+.1f}€/d) → {trend['recommendation']}")

            print()

    if contract:
        if direct:
            print("📋 **Vertrags-Deals:**\n")
        for i, h in enumerate(contract, 1):
            emoji = _emoji_for_model(h.get("normalized_model", ""))
            storage = f" {h['normalized_storage_gb']}GB" if h.get("normalized_storage_gb") else ""
            diff_sign = "+" if h["diff"] > 0 else ""

            monthly = h.get("contract_monthly")
            months = h.get("contract_months")
            upfront = h.get("contract_upfront")
            total = h.get("contract_total")
            price_detail = f"{upfront}€ + {months}×{monthly}€/mo = {total}€ eff." if all([upfront, monthly, months, total]) else f"eff. {total}€"

            print(f"{i}. {emoji} {h['normalized_model'].title()}{storage} — {price_detail} [{h['source']}]")
            print(f"   {h['deal_url']}")
            print(f"   🏷️ Geizhals: {h['geizhals_min']}€ → Diff: {diff_sign}{h['diff']}€")
            if h.get("geizhals_link"):
                print(f"   🔗 {h['geizhals_link']}")

            # Trend prediction
            trend = predict_trend(h.get("normalized_model", ""), days=30)
            if trend:
                trend_emoji = {"dropping": "📉", "stable": "📊", "rising": "📈"}.get(trend["trend"], "❓")
                print(f"   {trend_emoji} Trend: {trend['trend']} ({trend['slope_per_day']:+.1f}€/d) → {trend['recommendation']}")

            print()


def main():
    p = argparse.ArgumentParser(description="Deal Live Poll with deduplication")
    p.add_argument("--max-pages", type=int, default=15)
    p.add_argument("--max-checks", type=int, default=60)
    p.add_argument("--min-diff", type=float, default=15.0)
    p.add_argument("--out", choices=["alert", "json"], default="alert")
    p.add_argument("--reset", action="store_true", help="Clear sent deals history")
    args = p.parse_args()

    if args.reset:
        save_sent(set())
        print("Sent deals history cleared.", file=sys.stderr)

    result = run_poll(max_pages=args.max_pages, max_checks=args.max_checks, min_diff=args.min_diff)

    if args.out == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_alert(result["new_hits"])


if __name__ == "__main__":
    main()
