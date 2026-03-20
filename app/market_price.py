import json
import random
import re
import time
from pathlib import Path
from typing import Optional, Protocol

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "state" / "price_cache.json"

BASE_MODEL_PRICES = {
    "iphone 15": 760.0,
    "iphone 15 pro": 980.0,
    "iphone 15 pro max": 1130.0,
    "galaxy s24": 760.0,
    "galaxy s24 plus": 900.0,
    "galaxy s24 ultra": 1040.0,
    "pixel 8": 620.0,
    "pixel 8 pro": 760.0,
}


class MarketPriceProvider(Protocol):
    def estimate(self, deal: dict) -> Optional[float]:
        ...


def _query_from_deal(deal: dict) -> Optional[str]:
    model = (deal.get("normalized_model") or "").strip()
    if not model:
        return None

    storage = deal.get("normalized_storage_gb")
    if storage:
        try:
            return f"{model} {int(storage)}gb"
        except Exception:
            return model
    return model


def _query_variants_from_deal(deal: dict) -> list[str]:
    model = (deal.get("normalized_model") or "").strip()
    if not model:
        return []

    variants = []
    storage = deal.get("normalized_storage_gb")
    if storage:
        try:
            variants.append(f"{model} {int(storage)}gb")
            variants.append(f"{model} {int(storage)}")
        except Exception:
            pass
    variants.append(model)

    # Brand-prefixed fallbacks help with selective anti-bot/search behavior.
    ml = model.lower()
    if ml.startswith("pixel"):
        if storage:
            try:
                variants.append(f"google {model} {int(storage)}gb")
                variants.append(f"google {model} {int(storage)}")
            except Exception:
                pass
        variants.append(f"google {model}")

    seen = set()
    out = []
    for v in variants:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def _parse_number(raw: str) -> Optional[float]:
    if "," in raw and "." in raw:
        val = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        tail = raw.split(",")[-1]
        if len(tail) == 2:
            val = raw.replace(",", ".")
        else:
            val = raw.replace(",", "")
    else:
        parts = raw.split(".")
        if len(parts) > 1 and len(parts[-1]) == 2:
            val = raw
        else:
            val = raw.replace(".", "")
    try:
        return float(val)
    except Exception:
        return None


def _extract_eur_prices(text: str) -> list[float]:
    t = (text or "").replace("\u00a0", " ")
    prices = []

    patterns = [
        r"(\d{1,5}(?:[\.,]\d{3})*(?:[\.,]\d{2})?)\s?€",  # 1099€ / 1.099,00 €
        r"€\s?(\d{1,5}(?:[\.,]\d{3})*(?:[\.,]\d{2})?)",  # € 1099,00
    ]
    for pat in patterns:
        for m in re.finditer(pat, t):
            p = _parse_number(m.group(1))
            if p is None:
                continue
            if 20 <= p <= 20000:
                prices.append(p)

    return prices


def _extract_prices_near_query(text: str, query: str) -> list[float]:
    lines = text.splitlines()

    raw_tokens = [tok for tok in re.split(r"\s+", (query or "").lower()) if tok]
    tokens = []
    for tok in raw_tokens:
        clean = tok.strip(" ,.;:()[]{}")
        if clean in {"gb", "tb"}:
            continue
        if len(clean) >= 3 or any(ch.isdigit() for ch in clean):
            tokens.append(clean)

    if not tokens:
        return _extract_eur_prices(text)

    required_tokens = [t for t in tokens if any(ch.isdigit() for ch in t)]

    matched_chunks = []
    for i, line in enumerate(lines):
        l = line.lower()
        hits = sum(1 for t in tokens if t in l)
        has_required = True
        if required_tokens:
            has_required = any(t in l for t in required_tokens)

        if hits >= 2 and has_required:
            chunk = line
            if i + 1 < len(lines):
                chunk += "\n" + lines[i + 1]
            matched_chunks.append(chunk)

    if not matched_chunks:
        return []
    return _extract_eur_prices("\n".join(matched_chunks))


def _model_aliases(model: str) -> list[str]:
    m = (model or "").lower().strip()
    aliases = {m, m.replace(" ", "-")}

    if "plus" in m:
        aliases.add(m.replace("plus", "+"))
        aliases.add(m.replace("plus", "plus").replace(" ", ""))
    if "galaxy s24 plus" in m:
        aliases.update({"s24-plus", "s24+", "s926", "s926b"})
    if "galaxy s24 ultra" in m:
        aliases.update({"s24-ultra", "s24ultra", "s928", "s928b"})

    return [a for a in aliases if a]


def _extract_variant_rows(text: str, model: str, storage_gb: int | None = None) -> list[dict]:
    rows = []
    model_aliases = _model_aliases(model)
    storage_token = f"{int(storage_gb)}gb" if storage_gb else None

    pat = re.compile(
        r"ab\s*\[€\s*(\d{1,5}(?:[\.,]\d{2})?)\]\((https?://[^\)]+)\)",
        re.IGNORECASE,
    )

    for m in pat.finditer(text or ""):
        raw_price = m.group(1)
        url = m.group(2)
        ul = url.lower()

        if model_aliases and not any(alias in ul for alias in model_aliases):
            continue
        if storage_token and storage_token not in ul:
            continue
        if any(x in ul for x in ["case", "hülle", "schutzglas", "ladekabel", "netzteil", "cover"]):
            continue

        p = _parse_number(raw_price)
        if p is None or not (50 <= p <= 2500):
            continue

        rows.append({"price": round(p, 2), "url": url})

    dedup = {}
    for r in rows:
        dedup[r["url"]] = r
    return list(dedup.values())


def _cluster_prices(rows: list[dict], max_deviation_eur: float = 100.0) -> tuple[list[dict], list[dict], Optional[float], Optional[float], Optional[float]]:
    if not rows:
        return [], [], None, None, None

    prices = [r["price"] for r in rows]
    center = _robust_median(prices)
    if center is None:
        return [], rows, None, None, None

    inliers = [r for r in rows if abs(r["price"] - center) <= max_deviation_eur]
    outliers = [r for r in rows if abs(r["price"] - center) > max_deviation_eur]

    if not inliers:
        return [], rows, None, None, None

    sorted_prices = sorted(r["price"] for r in inliers)
    min_price = round(sorted_prices[0], 2)
    next_price = round(sorted_prices[1], 2) if len(sorted_prices) > 1 else None
    gap_to_next = round(next_price - min_price, 2) if next_price is not None else None
    return inliers, outliers, min_price, next_price, gap_to_next


def _robust_median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


class StaticTableMarketPriceProvider:
    def __init__(self, base_prices: dict[str, float] | None = None):
        self.base_prices = base_prices or BASE_MODEL_PRICES

    def estimate(self, deal: dict) -> Optional[float]:
        model = deal.get("normalized_model")
        if not model:
            return None

        base = self.base_prices.get(str(model).lower())
        if base is None:
            return None

        storage_gb = deal.get("normalized_storage_gb")
        if storage_gb is not None:
            try:
                storage_gb = int(storage_gb)
                if storage_gb >= 512:
                    base += 120
                elif storage_gb >= 256:
                    base += 60
            except Exception:
                pass

        return round(base, 2)


class WebSearchPriceProvider:
    """Best-effort generic provider for marketplace/listing pages via r.jina.ai mirror."""

    _last_request_ts: dict[str, float] = {}

    def __init__(self, base_url: str, source_name: str, min_ratio: float = 0.88, max_ratio: float = 1.2):
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio
        self._static_guard = StaticTableMarketPriceProvider()

    def _build_url(self, query: str) -> str:
        q = requests.utils.quote(query)
        return f"https://r.jina.ai/http://{self.base_url}/?q={q}"

    def _cache_get(self, cache_key: str, ttl_seconds: int = 6 * 3600):
        try:
            if not CACHE_PATH.exists():
                return None
            obj = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            item = obj.get(cache_key)
            if not item:
                return None
            if (time.time() - float(item.get("ts", 0))) > ttl_seconds:
                return None
            return item.get("value")
        except Exception:
            return None

    def _cache_set(self, cache_key: str, value):
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if CACHE_PATH.exists():
                data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            data[cache_key] = {"ts": time.time(), "value": value}
            # keep cache bounded
            if len(data) > 500:
                keys = sorted(data.keys(), key=lambda k: data[k].get("ts", 0), reverse=True)[:500]
                data = {k: data[k] for k in keys}
            CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _throttled_get(self, url: str):
        host = self.source_name
        now = time.time()
        last = self._last_request_ts.get(host, 0.0)
        min_interval = 1.2 + random.uniform(0.1, 0.5)
        wait = min_interval - (now - last)
        if wait > 0:
            time.sleep(wait)

        attempts = 2
        backoff = 1.0
        for i in range(attempts):
            try:
                r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
                self._last_request_ts[host] = time.time()
                if r.status_code == 429:
                    time.sleep(backoff + random.uniform(0.1, 0.4))
                    backoff *= 2
                    continue
                return r
            except Exception:
                if i == attempts - 1:
                    return None
                time.sleep(backoff + random.uniform(0.1, 0.4))
                backoff *= 2
        return None

    def _estimate_for_query(self, query: str, deal_for_sanity: dict) -> Optional[float]:
        url = self._build_url(query)
        cache_key = f"{self.source_name}:{query}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        r = self._throttled_get(url)
        if r is None or r.status_code != 200 or not r.text:
            return None

        if "Target URL returned error 429" in r.text or "Sicherheitsprüfung" in r.text:
            return None

        prices = _extract_prices_near_query(r.text, query)
        if not prices:
            return None

        prices = sorted(prices)
        if len(prices) >= 8:
            cut = max(1, int(len(prices) * 0.15))
            prices = prices[cut:-cut] or prices

        med = _robust_median(prices)
        if med is None:
            return None

        baseline = self._static_guard.estimate(deal_for_sanity)
        if baseline is not None:
            ratio = med / baseline if baseline > 0 else 1.0
            if ratio < self.min_ratio or ratio > self.max_ratio:
                return None

        value = round(med, 2)
        self._cache_set(cache_key, value)
        return value

    def estimate(self, deal: dict) -> Optional[float]:
        query = _query_from_deal(deal)
        if not query:
            return None
        return self._estimate_for_query(query, deal)


class GeizhalsProvider(WebSearchPriceProvider):
    def __init__(self):
        # geizhals works more reliably with `fs` search than `q` in this environment.
        super().__init__(base_url="geizhals.de", source_name="geizhals", min_ratio=0.65, max_ratio=1.35)

    def _build_url(self, query: str) -> str:
        q = requests.utils.quote(query)
        return f"https://r.jina.ai/http://geizhals.de/?fs={q}"

    def _build_urls(self, query: str) -> list[str]:
        q = requests.utils.quote(query)
        return [
            f"https://r.jina.ai/http://geizhals.de/?fs={q}",
            f"https://r.jina.ai/http://geizhals.at/?fs={q}",
        ]

    def _fetch_live_price_from_product_url(self, product_url: str) -> Optional[float]:
        try:
            clean = (product_url or "").strip()
            if not clean:
                return None
            mirror_url = "https://r.jina.ai/http://" + clean.replace("https://", "").replace("http://", "")
            cache_key = f"geizhals_live:{clean}"
            cached = self._cache_get(cache_key, ttl_seconds=2 * 3600)
            if cached is not None:
                return cached

            r = self._throttled_get(mirror_url)
            if r is None or r.status_code != 200 or not r.text:
                return None

            prices = [p for p in _extract_eur_prices(r.text) if 50 <= p <= 5000]
            if not prices:
                return None

            live = round(min(prices), 2)
            self._cache_set(cache_key, live)
            return live
        except Exception:
            return None

    def estimate_with_variants(self, deal: dict) -> dict:
        model = (deal.get("normalized_model") or "").strip().lower()
        storage = deal.get("normalized_storage_gb")
        attempts = []

        for q in _query_variants_from_deal(deal):
            for url in self._build_urls(q):
                r = self._throttled_get(url)
                text = r.text if (r is not None and r.status_code == 200) else ""

                variants = _extract_variant_rows(text, model=model, storage_gb=storage)

                # Enrich with product-page live prices for better click-time consistency.
                enriched = []
                for v in variants:
                    live_price = self._fetch_live_price_from_product_url(v.get("url"))
                    row = dict(v)
                    row["list_price"] = v.get("price")

                    # Guard: product pages may contain accessory prices; only accept plausible live drift.
                    if live_price is not None and row.get("list_price") is not None:
                        lp = float(row["list_price"])
                        if live_price < lp * 0.6 or live_price > lp * 1.4:
                            live_price = None

                    row["live_price"] = live_price
                    row["price"] = live_price if live_price is not None else v.get("price")
                    row["price_delta"] = (
                        round(row["price"] - row["list_price"], 2)
                        if row.get("price") is not None and row.get("list_price") is not None
                        else None
                    )
                    enriched.append(row)

                inliers, outliers, min_price, next_price, gap_to_next = _cluster_prices(enriched, max_deviation_eur=100.0)

                attempts.append({
                    "query": q,
                    "url": url,
                    "variant_count": len(variants),
                    "inlier_count": len(inliers),
                    "outlier_count": len(outliers),
                    "variants": sorted(variants, key=lambda x: x["price"]),
                    "inliers": sorted(inliers, key=lambda x: x["price"]),
                    "outliers": sorted(outliers, key=lambda x: x["price"]),
                    "price": min_price,
                    "next_price": next_price,
                    "gap_to_next": gap_to_next,
                })

                if min_price is not None:
                    return {"price": min_price, "attempts": attempts}

        return {"price": None, "attempts": attempts}

    def estimate(self, deal: dict) -> Optional[float]:
        return self.estimate_with_variants(deal).get("price")


class EbaySoldProvider:
    """Stub provider placeholder for future real sold-listings integration."""

    def estimate(self, deal: dict) -> Optional[float]:
        _ = deal
        return None


def build_provider(mode: str = "auto") -> MarketPriceProvider:
    mode = (mode or "auto").lower()
    if mode == "static":
        return StaticTableMarketPriceProvider()
    if mode == "ebay":
        return EbaySoldProvider()
    if mode == "geizhals":
        return GeizhalsProvider()
    if mode == "auto":
        return ChainedMarketPriceProvider(
            [GeizhalsProvider(), EbaySoldProvider(), StaticTableMarketPriceProvider()]
        )
    raise ValueError(f"Unsupported provider mode: {mode}")


class ChainedMarketPriceProvider:
    def __init__(self, providers: list[MarketPriceProvider]):
        self.providers = providers

    def estimate(self, deal: dict) -> Optional[float]:
        for p in self.providers:
            value = p.estimate(deal)
            if value is not None:
                return value
        return None


def estimate_market_price(deal: dict, provider: MarketPriceProvider | None = None) -> Optional[float]:
    provider = provider or build_provider("auto")
    return provider.estimate(deal)


def estimate_market_price_debug(deal: dict, mode: str = "auto") -> dict:
    """Debug helper: returns price plus attempted source URLs for manual verification."""
    mode = (mode or "auto").lower()
    providers = []
    if mode == "auto":
        providers = [GeizhalsProvider(), EbaySoldProvider(), StaticTableMarketPriceProvider()]
    else:
        providers = [build_provider(mode)]

    attempts = []
    for p in providers:
        info = {"provider": p.__class__.__name__, "query": None, "url": None, "price": None}
        if isinstance(p, GeizhalsProvider):
            g = p.estimate_with_variants(deal)
            attempts.extend(
                {
                    "provider": p.__class__.__name__,
                    "query": a.get("query"),
                    "url": a.get("url"),
                    "price": a.get("price"),
                    "variant_count": a.get("variant_count"),
                    "inlier_count": a.get("inlier_count"),
                    "outlier_count": a.get("outlier_count"),
                    "variants": a.get("variants"),
                    "inliers": a.get("inliers"),
                    "outliers": a.get("outliers"),
                    "next_price": a.get("next_price"),
                    "gap_to_next": a.get("gap_to_next"),
                }
                for a in g.get("attempts", [])
            )
            if g.get("price") is not None:
                return {"price": g.get("price"), "attempts": attempts}
            continue

        if isinstance(p, WebSearchPriceProvider):
            q = _query_from_deal(deal)
            info["query"] = q
            info["url"] = p._build_url(q) if q else None
            value = p.estimate(deal)
            info["price"] = value
            attempts.append(info)
            if value is not None:
                return {"price": value, "attempts": attempts}
            continue

        value = p.estimate(deal)
        info["price"] = value
        attempts.append(info)
        if value is not None:
            return {"price": value, "attempts": attempts}

    return {"price": None, "attempts": attempts}


def estimate_profit(
    buy_price: float,
    market_price: float,
    fee_rate: float = 0.12,
    shipping_cost: float = 6.0,
    risk_discount_rate: float = 0.05,
) -> float:
    net_sale = market_price * (1 - fee_rate)
    risk_discount = market_price * risk_discount_rate
    profit = net_sale - buy_price - shipping_cost - risk_discount
    return round(profit, 2)
