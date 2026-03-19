from typing import Optional


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


def estimate_market_price(deal: dict) -> Optional[float]:
    model = deal.get("normalized_model")
    if not model:
        return None

    base = BASE_MODEL_PRICES.get(str(model).lower())
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
