import re
from typing import Optional, Protocol

import requests


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
        except Exception:
            pass
    variants.append(model)

    # dedupe while preserving order
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
        # keep semantic words (len>=3) and model numbers like s24 / 15 / 8
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

    def __init__(self, base_url: str, source_name: str, min_ratio: float = 0.88, max_ratio: float = 1.2):
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio
        self._static_guard = StaticTableMarketPriceProvider()

    def _build_url(self, query: str) -> str:
        q = requests.utils.quote(query)
        return f"https://r.jina.ai/http://{self.base_url}/?q={q}"

    def _estimate_for_query(self, query: str, deal_for_sanity: dict) -> Optional[float]:
        url = self._build_url(query)
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or not r.text:
                return None
        except Exception:
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

        return round(med, 2)

    def estimate(self, deal: dict) -> Optional[float]:
        query = _query_from_deal(deal)
        if not query:
            return None
        return self._estimate_for_query(query, deal)


class IdealoProvider(WebSearchPriceProvider):
    def __init__(self):
        super().__init__(base_url="www.idealo.de/preisvergleich/MainSearchProductCategory.html", source_name="idealo")


class GeizhalsProvider(WebSearchPriceProvider):
    def __init__(self):
        # geizhals works more reliably with `fs` search than `q` in this environment.
        super().__init__(base_url="geizhals.de", source_name="geizhals", min_ratio=0.72, max_ratio=1.28)

    def _build_url(self, query: str) -> str:
        q = requests.utils.quote(query)
        return f"https://r.jina.ai/http://geizhals.de/?fs={q}"

    def estimate(self, deal: dict) -> Optional[float]:
        # Try with storage first, then relaxed model-only query.
        for q in _query_variants_from_deal(deal):
            value = self._estimate_for_query(q, deal)
            if value is not None:
                return value
        return None


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
    if mode == "idealo":
        return IdealoProvider()
    if mode == "geizhals":
        return GeizhalsProvider()
    if mode == "auto":
        return ChainedMarketPriceProvider(
            [IdealoProvider(), GeizhalsProvider(), EbaySoldProvider(), StaticTableMarketPriceProvider()]
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
