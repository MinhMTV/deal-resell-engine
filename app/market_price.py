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


def _extract_eur_prices(text: str) -> list[float]:
    t = (text or "").replace("\u00a0", " ")
    prices = []

    for m in re.finditer(r"(\d{1,5}(?:[\.,]\d{3})*(?:[\.,]\d{2})?)\s?€", t):
        raw = m.group(1)
        if "," in raw and "." in raw:
            # Assume . as thousands and , as decimals in EU format.
            val = raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            # Could be decimals or thousands, infer by suffix length.
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
            p = float(val)
        except Exception:
            continue
        if 20 <= p <= 20000:
            prices.append(p)

    return prices


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

    def __init__(self, base_url: str, source_name: str):
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name

    def _build_url(self, query: str) -> str:
        q = requests.utils.quote(query)
        return f"https://r.jina.ai/http://{self.base_url}/?q={q}"

    def estimate(self, deal: dict) -> Optional[float]:
        query = _query_from_deal(deal)
        if not query:
            return None

        url = self._build_url(query)
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or not r.text:
                return None
        except Exception:
            return None

        prices = _extract_eur_prices(r.text)
        if not prices:
            return None

        # lightweight denoise: trim top/bottom 15% when enough samples
        prices = sorted(prices)
        if len(prices) >= 8:
            cut = max(1, int(len(prices) * 0.15))
            prices = prices[cut:-cut] or prices

        med = _robust_median(prices)
        return round(med, 2) if med is not None else None


class IdealoProvider(WebSearchPriceProvider):
    def __init__(self):
        super().__init__(base_url="www.idealo.de/preisvergleich/MainSearchProductCategory.html", source_name="idealo")


class GeizhalsProvider(WebSearchPriceProvider):
    def __init__(self):
        super().__init__(base_url="geizhals.de", source_name="geizhals")


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
