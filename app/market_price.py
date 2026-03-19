from typing import Optional, Protocol


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


class EbaySoldProvider:
    """Stub provider placeholder for future real sold-listings integration."""

    def estimate(self, deal: dict) -> Optional[float]:
        # TODO: replace with real API/client integration.
        # For now, intentionally return no estimate.
        _ = deal
        return None


def build_provider(mode: str = "auto") -> MarketPriceProvider:
    mode = (mode or "auto").lower()
    if mode == "static":
        return StaticTableMarketPriceProvider()
    if mode == "ebay":
        return EbaySoldProvider()
    if mode == "auto":
        return ChainedMarketPriceProvider([EbaySoldProvider(), StaticTableMarketPriceProvider()])
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
