#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from app.config import DB_PATH, MIN_SCORE
from app.storage import (
    connect,
    upsert_deal,
    top_deals,
    iter_deals_missing_normalization,
    update_normalization,
)
from app.intake import fetch_live_source, fetch_sample, load_cursors, save_cursors, detect_contract_deal, detect_bundle_deal
from app.scoring import score_deal
from app.normalize import normalize_product
from app.market_price import estimate_market_price, estimate_profit, build_provider, estimate_market_price_debug

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETRY_QUEUE_PATH = PROJECT_ROOT / "state" / "retry_queue.json"


def _build_alert_key(source: str, normalized_model: str | None, url: str) -> str:
    model = normalized_model or "unknown-model"
    url_hash = hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:10]
    return f"{source}:{model}:{url_hash}"


def cmd_ingest(args):
    conn = connect(args.db)
    deals = []
    errors = []

    if args.mode == "sample":
        deals = fetch_sample(args.sample)
    else:
        cursors = load_cursors()
        for src in ["mydealz", "preisjaeger"]:
            stop_url = cursors.get(src) if args.new_only else None
            rows, err = fetch_live_source(src, stop_url=stop_url, max_pages=args.max_pages)
            deals.extend(rows)
            if rows:
                cursors[src] = rows[0]["url"]
            if err:
                errors.append(err)
        save_cursors(cursors)

    for d in deals:
        d.update(normalize_product(d.get("title", "")))
        score, reasons = score_deal(d)
        d["score"] = score
        d["reasons"] = reasons
        upsert_deal(conn, d)

    print(f"Ingested: {len(deals)} deals")
    if errors:
        print("Warnings:")
        for e in errors:
            print(f"- {e}")


def cmd_report(args):
    conn = connect(args.db)
    rows = top_deals(conn, min_score=args.min_score, limit=args.limit, days=args.days)
    if not rows:
        print("No deals above threshold.")
        return
    for i, r in enumerate(rows, 1):
        (
            src,
            title,
            url,
            price,
            votes,
            score,
            reasons,
            normalized_brand,
            normalized_model,
            normalized_storage_gb,
            normalized_color,
        ) = r
        print(
            f"{i}. [{src}] score={score} price={price} votes={votes} :: {title}\n"
            f"   {url}\n"
            f"   normalized: brand={normalized_brand} model={normalized_model} storage_gb={normalized_storage_gb} color={normalized_color}\n"
            f"   reasons: {reasons}"
        )


def cmd_backfill_normalization(args):
    conn = connect(args.db)
    rows = iter_deals_missing_normalization(conn, limit=args.limit)
    updated = 0
    for deal_id, title in rows:
        normalized = normalize_product(title or "")
        update_normalization(conn, deal_id, normalized)
        updated += 1
    print(f"Backfilled normalization for: {updated} deals")


def cmd_profit_report(args):
    conn = connect(args.db)
    rows = top_deals(conn, min_score=args.min_score, limit=args.limit, days=args.days)
    if not rows:
        if args.out == "json":
            print("[]")
        else:
            print("No deals above threshold.")
        return

    candidates = []

    for r in rows:
        (
            src,
            title,
            url,
            price,
            votes,
            score,
            reasons,
            normalized_brand,
            normalized_model,
            normalized_storage_gb,
            normalized_color,
        ) = r

        deal = {
            "normalized_model": normalized_model,
            "normalized_storage_gb": normalized_storage_gb,
        }

        # Use debug mode to get Geizhals link + details
        debug = estimate_market_price_debug(deal, mode=args.provider)
        market_price = debug.get("price")
        if market_price is None or price is None:
            continue

        # Extract Geizhals link from debug attempts
        geizhals_link = None
        geizhals_min = None
        best_attempt = next(
            (a for a in debug.get("attempts", []) if a.get("price") is not None), None
        )
        if best_attempt:
            geizhals_min = best_attempt.get("price")
            if best_attempt.get("inliers"):
                geizhals_link = best_attempt["inliers"][0].get("url")
            elif best_attempt.get("url"):
                geizhals_link = best_attempt["url"]

        buy_price = float(price)
        profit = estimate_profit(buy_price, market_price)
        if profit < args.min_profit:
            continue

        roi_pct = (profit / buy_price * 100.0) if buy_price > 0 else 0.0
        if args.min_roi is not None and roi_pct < args.min_roi:
            continue

        diff = round(market_price - buy_price, 2) if market_price and buy_price else None

        candidates.append(
            {
                "src": src,
                "title": title,
                "url": url,
                "price": price,
                "votes": votes,
                "score": score,
                "reasons": reasons,
                "normalized_brand": normalized_brand,
                "normalized_model": normalized_model,
                "normalized_storage_gb": normalized_storage_gb,
                "normalized_color": normalized_color,
                "market_price": market_price,
                "profit": profit,
                "roi_pct": round(roi_pct, 2),
                "geizhals_min": geizhals_min,
                "geizhals_link": geizhals_link,
                "diff": diff,
            }
        )

    if not candidates:
        if args.out == "json":
            print("[]")
        else:
            print("No deals matching profit criteria.")
        return

    if args.sort_by == "profit":
        candidates.sort(key=lambda x: (x["profit"], x["score"]), reverse=True)
    else:
        candidates.sort(key=lambda x: (x["score"], x["profit"]), reverse=True)

    if args.top is not None:
        candidates = candidates[: max(0, int(args.top))]

    if args.out == "json":
        payload = candidates
        if args.json_schema == "alert":
            payload = [
                {
                    "alert_key": _build_alert_key(c["src"], c["normalized_model"], c["url"]),
                    "source": c["src"],
                    "normalized_model": c["normalized_model"],
                    "title": c["title"],
                    "url": c["url"],
                    "profit": c["profit"],
                    "roi_pct": c["roi_pct"],
                    "score": c["score"],
                    "geizhals_min": c.get("geizhals_min"),
                    "geizhals_link": c.get("geizhals_link"),
                    "diff": c.get("diff"),
                }
                for c in candidates
            ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    for i, c in enumerate(candidates, 1):
        geizhals_info = ""
        if c.get("geizhals_min") is not None:
            diff_str = f"+{c['diff']}€" if c.get("diff") and c["diff"] > 0 else f"{c.get('diff', 0)}€"
            geizhals_info = f"\n   geizhals: {c['geizhals_min']}€ min | diff: {diff_str}"
            if c.get("geizhals_link"):
                geizhals_info += f" | {c['geizhals_link']}"

        print(
            f"{i}. [{c['src']}] score={c['score']} buy={c['price']}€ market≈{c['market_price']}€ profit≈{c['profit']}€ roi≈{c['roi_pct']}% :: {c['title']}\n"
            f"   {c['url']}{geizhals_info}\n"
            f"   normalized: brand={c['normalized_brand']} model={c['normalized_model']} storage_gb={c['normalized_storage_gb']} color={c['normalized_color']}\n"
            f"   reasons: {c['reasons']}"
        )


def cmd_price_check(args):
    deal = {
        "normalized_model": args.model,
        "normalized_storage_gb": args.storage,
    }
    debug = estimate_market_price_debug(deal, mode=args.provider)
    print(json.dumps(debug, ensure_ascii=False, indent=2))


def _load_retry_queue():
    if not RETRY_QUEUE_PATH.exists():
        return []
    try:
        return json.loads(RETRY_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_retry_queue(rows):
    RETRY_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RETRY_QUEUE_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_market_compare(args):
    all_deals = []
    for src in ["mydealz", "preisjaeger"]:
        rows, err = fetch_live_source(src, stop_url=None, max_pages=args.max_pages)
        if err:
            print(f"WARN: {err}")
        all_deals.extend(rows)

    hits = []
    retry_queue = []
    checked = 0

    for d in all_deals:
        if checked >= args.max_checks:
            break
        price = d.get("price")
        if price is None:
            continue

        # Detect contract deals and extract effective pricing
        d = detect_contract_deal(d)
        d = detect_bundle_deal(d)
        is_contract = d.get("is_contract", False)
        contract_total = d.get("contract_total")
        if is_contract and contract_total is not None:
            effective_price = float(contract_total)
        else:
            effective_price = float(price)
            is_contract = False  # no usable total → treat as direct
        compare_price = effective_price  # use effective total for Geizhals comparison

        normalized = normalize_product(d.get("title", ""))
        model = normalized.get("normalized_model")
        if not model:
            continue

        checked += 1
        deal_input = {
            "normalized_model": model,
            "normalized_storage_gb": normalized.get("normalized_storage_gb"),
        }
        debug = estimate_market_price_debug(deal_input, mode="geizhals")
        geizhals_min = debug.get("price")

        best_attempt = next((a for a in debug.get("attempts", []) if a.get("price") is not None), None)
        geizhals_link = None
        if best_attempt and best_attempt.get("inliers"):
            geizhals_link = best_attempt["inliers"][0].get("url")
        elif best_attempt and best_attempt.get("method") == "text_fallback":
            geizhals_link = best_attempt.get("url")
        # Also check for product_url in debug result (text fallback)
        if geizhals_link is None:
            geizhals_link = debug.get("product_url")

        if geizhals_min is None:
            retry_queue.append(
                {
                    "source": d.get("source"),
                    "title": d.get("title"),
                    "url": d.get("url"),
                    "price": price,
                    "normalized_model": model,
                    "normalized_storage_gb": normalized.get("normalized_storage_gb"),
                    "is_contract": is_contract,
                    "contract_total": d.get("contract_total"),
                    "added_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            continue

        diff = round(float(geizhals_min) - compare_price, 2)
        if diff >= args.min_diff:
            hit = {
                "source": d.get("source"),
                "title": d.get("title"),
                "deal_url": d.get("url"),
                "deal_price": float(price),
                "effective_price": effective_price if is_contract else None,
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
                "next_price": best_attempt.get("next_price") if best_attempt else None,
                "gap_to_next": best_attempt.get("gap_to_next") if best_attempt else None,
                "diff": diff,
            }
            hits.append(hit)

    _save_retry_queue(retry_queue)

    hits.sort(key=lambda x: x["diff"], reverse=True)

    if args.out == "json":
        print(json.dumps({"checked": checked, "hits": hits, "retry_queue": len(retry_queue)}, ensure_ascii=False, indent=2))
        return

    if args.out == "alert":
        _print_alert_format(hits[: args.limit], checked, len(retry_queue))
        return

    print(f"Checked model deals: {checked}")
    print(f"Hits >= {args.min_diff}€: {len(hits)}")
    print(f"Retry queue entries: {len(retry_queue)}")
    for i, h in enumerate(hits[: args.limit], 1):
        storage = f" {h['normalized_storage_gb']}GB" if h.get("normalized_storage_gb") else ""

        # Price display
        if h.get("is_contract"):
            price_line = f"eff. {h['contract_total']}€ ({h['contract_upfront']}€ + {h['contract_months']}×{h['contract_monthly']}€/mo)"
        else:
            price_line = f"{h['deal_price']}€"

        geizhals_line = ""
        if h.get("geizhals_min") is not None:
            diff_sign = "+" if h["diff"] > 0 else ""
            geizhals_line = f"\n   🏷️ Geizhals: {h['geizhals_min']}€ min → diff: {diff_sign}{h['diff']}€"
            if h.get("geizhals_link"):
                geizhals_line += f"\n   🔗 {h['geizhals_link']}"
            if h.get("next_price"):
                geizhals_line += f"\n   📊 nächster Preis: {h['next_price']}€ (Gap: {h['gap_to_next']}€)"

        tag = "📋 Vertrag | " if h.get("is_contract") else ""
        bundle_warn = f" ⚠️ Bundle ({h['bundle_reason']})" if h.get("is_bundle") else ""
        print(
            f"{i}. [{h['source']}] {tag}{h['normalized_model']}{storage} — {price_line}{bundle_warn}\n"
            f"   {h['deal_url']}{geizhals_line}"
        )


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


def _print_alert_format(hits: list[dict], checked: int, retry_count: int):
    """Telegram-ready alert format with Geizhals data per deal."""
    if not hits:
        return

    # Split into contract and non-contract
    contract_hits = [h for h in hits if h.get("is_contract")]
    direct_hits = [h for h in hits if not h.get("is_contract")]

    print(f"🔥 {len(hits)} neue Deal-Treffer gefunden ({checked} geprüft):\n")

    if direct_hits:
        print("📦 **Direktkauf-Deals:**\n")
        for i, h in enumerate(direct_hits, 1):
            emoji = _emoji_for_model(h.get("normalized_model", ""))
            storage = f" {h['normalized_storage_gb']}GB" if h.get("normalized_storage_gb") else ""
            diff_sign = "+" if h.get("diff", 0) > 0 else ""
            bundle_warn = f" ⚠️ Bundle ({h['bundle_reason']})" if h.get("is_bundle") else ""

            print(f"{i}. {emoji} {h['normalized_model'].title()}{storage} — {h['deal_price']}€ [{h['source']}]{bundle_warn}")
            print(f"   {h['deal_url']}")
            if h.get("geizhals_min") is not None:
                print(f"   🏷️ Geizhals min: {h['geizhals_min']}€ → Diff: {diff_sign}{h['diff']}€")
                if h.get("geizhals_link"):
                    print(f"   🔗 {h['geizhals_link']}")
            else:
                print(f"   ⚠️ Geizhals: kein Match")
            print()

    if contract_hits:
        print("📋 **Vertrags-Deals (eff. Gesamtpreis):**\n")
        for i, h in enumerate(contract_hits, 1):
            emoji = _emoji_for_model(h.get("normalized_model", ""))
            storage = f" {h['normalized_storage_gb']}GB" if h.get("normalized_storage_gb") else ""
            diff_sign = "+" if h.get("diff", 0) > 0 else ""

            monthly = h.get("contract_monthly")
            months = h.get("contract_months")
            upfront = h.get("contract_upfront")
            total = h.get("contract_total")

            price_detail = f"{upfront}€ + {months}×{monthly}€/mo = {total}€ eff." if all([upfront, monthly, months, total]) else f"eff. {total}€"

            print(f"{i}. {emoji} {h['normalized_model'].title()}{storage} — {price_detail} [{h['source']}]")
            print(f"   {h['deal_url']}")
            if h.get("geizhals_min") is not None:
                print(f"   🏷️ Geizhals min: {h['geizhals_min']}€ → Diff: {diff_sign}{h['diff']}€")
                if h.get("geizhals_link"):
                    print(f"   🔗 {h['geizhals_link']}")
            else:
                print(f"   ⚠️ Geizhals: kein Match")
            print()

    if retry_count > 0:
        print(f"⏳ {retry_count} Deals in Retry-Queue (Geizhals kein Match, wird nachgeprüft)")


def main():
    p = argparse.ArgumentParser(description="Deal Resell Engine (rule-based MVP)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest")
    ing.add_argument("--mode", choices=["sample", "live"], default="sample")
    ing.add_argument("--sample", default="samples/deals_sample.json")
    ing.add_argument("--db", default=DB_PATH)
    ing.add_argument("--new-only", action="store_true", default=False)
    ing.add_argument("--max-pages", type=int, default=1, help="Fallback pagination depth for live intake (e.g. 10)")
    ing.set_defaults(func=cmd_ingest)

    rep = sub.add_parser("report")
    rep.add_argument("--db", default=DB_PATH)
    rep.add_argument("--min-score", type=float, default=MIN_SCORE)
    rep.add_argument("--limit", type=int, default=10)
    rep.add_argument("--days", type=int, default=7)
    rep.set_defaults(func=cmd_report)

    backfill = sub.add_parser("backfill-normalization")
    backfill.add_argument("--db", default=DB_PATH)
    backfill.add_argument("--limit", type=int, default=500)
    backfill.set_defaults(func=cmd_backfill_normalization)

    price_check = sub.add_parser("price-check")
    price_check.add_argument("--model", required=True, help="Normalized model, e.g. 'galaxy s24 ultra'")
    price_check.add_argument("--storage", type=int, default=None, help="Storage in GB, e.g. 256")
    price_check.add_argument("--provider", choices=["auto", "static", "ebay", "geizhals"], default="auto")
    price_check.set_defaults(func=cmd_price_check)

    mcmp = sub.add_parser("market-compare")
    mcmp.add_argument("--max-pages", type=int, default=10)
    mcmp.add_argument("--max-checks", type=int, default=40)
    mcmp.add_argument("--min-diff", type=float, default=20.0)
    mcmp.add_argument("--limit", type=int, default=10)
    mcmp.add_argument("--out", choices=["text", "json", "alert"], default="text")
    mcmp.set_defaults(func=cmd_market_compare)

    profit = sub.add_parser("profit-report")
    profit.add_argument("--db", default=DB_PATH)
    profit.add_argument("--min-score", type=float, default=MIN_SCORE)
    profit.add_argument("--limit", type=int, default=10)
    profit.add_argument("--days", type=int, default=7)
    profit.add_argument("--provider", choices=["auto", "static", "ebay", "geizhals"], default="auto")
    profit.add_argument("--min-profit", type=float, default=0.0)
    profit.add_argument("--min-roi", type=float, default=None, help="Minimum ROI percent, e.g. 10 for 10%%")
    profit.add_argument("--sort-by", choices=["score", "profit"], default="score")
    profit.add_argument("--top", type=int, default=None)
    profit.add_argument("--out", choices=["text", "json"], default="text")
    profit.add_argument("--json-schema", choices=["full", "alert"], default="full")
    profit.set_defaults(func=cmd_profit_report)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
