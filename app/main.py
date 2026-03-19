#!/usr/bin/env python3
import argparse
from app.config import DB_PATH, MIN_SCORE
from app.storage import (
    connect,
    upsert_deal,
    top_deals,
    iter_deals_missing_normalization,
    update_normalization,
)
from app.intake import fetch_live_source, fetch_sample, load_cursors, save_cursors
from app.scoring import score_deal
from app.normalize import normalize_product
from app.market_price import estimate_market_price, estimate_profit


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
            rows, err = fetch_live_source(src, stop_url=stop_url)
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

        deal = {
            "normalized_model": normalized_model,
            "normalized_storage_gb": normalized_storage_gb,
        }
        market_price = estimate_market_price(deal)
        if market_price is None or price is None:
            print(f"{i}. [{src}] score={score} :: {title}\n   {url}\n   profit_estimate: unavailable")
            continue

        profit = estimate_profit(float(price), market_price)
        print(
            f"{i}. [{src}] score={score} buy={price} market≈{market_price} profit≈{profit} :: {title}\n"
            f"   {url}\n"
            f"   normalized: brand={normalized_brand} model={normalized_model} storage_gb={normalized_storage_gb} color={normalized_color}\n"
            f"   reasons: {reasons}"
        )


def main():
    p = argparse.ArgumentParser(description="Deal Resell Engine (rule-based MVP)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest")
    ing.add_argument("--mode", choices=["sample", "live"], default="sample")
    ing.add_argument("--sample", default="samples/deals_sample.json")
    ing.add_argument("--db", default=DB_PATH)
    ing.add_argument("--new-only", action="store_true", default=False)
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

    profit = sub.add_parser("profit-report")
    profit.add_argument("--db", default=DB_PATH)
    profit.add_argument("--min-score", type=float, default=MIN_SCORE)
    profit.add_argument("--limit", type=int, default=10)
    profit.add_argument("--days", type=int, default=7)
    profit.set_defaults(func=cmd_profit_report)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
