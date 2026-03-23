"""Amazon price lookup for cross-platform comparison.

Uses web search to find Amazon prices for products.
Provides a second data point alongside Geizhals.
"""

import re
import requests
from typing import Optional


def _extract_amazon_price(text: str) -> Optional[float]:
    """Extract the first plausible Amazon price from text."""
    # Amazon format: '€XXX,XX' or 'EUR XXX,XX' or just 'XXX,XX'
    patterns = [
        r"€\s*(\d{1,5}[\.,]\d{2})",
        r"(\d{1,5}[\.,]\d{2})\s*€",
        r"EUR\s*(\d{1,5}[\.,]\d{2})",
    ]
    prices = []
    for p in patterns:
        for m in re.finditer(p, text):
            val = float(m.group(1).replace(",", "."))
            if 20 <= val <= 5000:
                prices.append(val)
    if not prices:
        return None
    return round(min(prices), 2)


def lookup_amazon_price(model: str, storage_gb: int | None = None) -> dict:
    """
    Look up Amazon price for a product via web search.
    Returns dict with price, url, and source info.
    """
    query = model
    if storage_gb:
        query = f"{model} {storage_gb}gb"

    # Use Jina to search Amazon
    search_url = f"https://r.jina.ai/http://www.amazon.de/s?k={requests.utils.quote(query + ' kaufen')}"

    try:
        r = requests.get(search_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.text:
            return {"price": None, "url": None, "source": "amazon", "error": f"HTTP {r.status_code}"}

        price = _extract_amazon_price(r.text)

        # Try to find an actual Amazon product URL
        amazon_url = None
        url_match = re.search(r"(https?://(?:www\.)?amazon\.de/[^\s\"<>]+/dp/[A-Z0-9]{10})", r.text)
        if url_match:
            amazon_url = url_match.group(1)

        return {
            "price": price,
            "url": amazon_url,
            "source": "amazon",
            "query": query,
        }
    except Exception as e:
        return {"price": None, "url": None, "source": "amazon", "error": str(e)}


def compare_platforms(deal_price: float, geizhals_min: float | None, amazon_price: float | None) -> dict:
    """Compare deal price against multiple market prices."""
    comparisons = {}

    if geizhals_min is not None:
        comparisons["geizhals"] = {
            "price": geizhals_min,
            "diff": round(geizhals_min - deal_price, 2),
            "savings_pct": round((1 - deal_price / geizhals_min) * 100, 1) if geizhals_min > 0 else 0,
        }

    if amazon_price is not None:
        comparisons["amazon"] = {
            "price": amazon_price,
            "diff": round(amazon_price - deal_price, 2),
            "savings_pct": round((1 - deal_price / amazon_price) * 100, 1) if amazon_price > 0 else 0,
        }

    # Find best comparison
    best = None
    for platform, data in comparisons.items():
        if best is None or data["diff"] > best["diff"]:
            best = {"platform": platform, **data}

    return {
        "deal_price": deal_price,
        "comparisons": comparisons,
        "best": best,
    }


def format_comparison(compare: dict) -> str:
    """Format platform comparison as a readable line."""
    parts = []
    for platform, data in compare.get("comparisons", {}).items():
        sign = "+" if data["diff"] >= 0 else ""
        parts.append(f"{platform}: {data['price']}€ ({sign}{data['diff']}€, {sign}{data['savings_pct']}%)")
    return " vs ".join(parts)
