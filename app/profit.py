"""Net profit calculation with platform-specific fees, shipping, and risk.

Supported platforms:
- ebay: ~12.5% commission + PayPal 2.49% + ~5€ shipping
- kleinanzeigen: ~10% commission + ~0€ shipping (local)
- local: 0% fees, pickup only
"""

import re

# Platform fee structures (% of sale price)
PLATFORM_FEES = {
    "ebay": {
        "commission_pct": 12.5,
        "payment_pct": 2.49,
        "listing_fee": 0.0,
        "avg_shipping": 5.99,
    },
    "kleinanzeigen": {
        "commission_pct": 10.0,
        "payment_pct": 0.0,
        "listing_fee": 0.0,
        "avg_shipping": 0.0,
    },
    "local": {
        "commission_pct": 0.0,
        "payment_pct": 0.0,
        "listing_fee": 0.0,
        "avg_shipping": 0.0,
    },
}

# Risk discount: items above this threshold get a risk adjustment
RISK_THRESHOLDS = [
    (2000, 0.05),   # >2000€: 5% risk discount
    (1000, 0.03),   # >1000€: 3%
    (500, 0.02),    # >500€: 2%
    (0, 0.01),      # default: 1%
]


def get_risk_discount(sale_price: float) -> float:
    """Return risk discount percentage based on sale price."""
    for threshold, discount in RISK_THRESHOLDS:
        if sale_price >= threshold:
            return discount
    return 0.01


def calculate_net_profit(
    buy_price: float,
    sale_price: float,
    platform: str = "ebay",
    custom_shipping: float | None = None,
) -> dict:
    """
    Calculate net profit after all fees, shipping, and risk.

    Returns dict with:
    - buy_price: what you pay
    - sale_price: what you sell for
    - gross_profit: sale - buy
    - platform_fees: total platform costs
    - shipping: shipping cost
    - risk_adjustment: risk-based discount on sale price
    - net_profit: actual profit after everything
    - roi_pct: return on investment
    - margin_pct: profit as % of sale price
    - breakdown: detailed fee breakdown
    """
    platform = (platform or "ebay").lower()
    fees = PLATFORM_FEES.get(platform, PLATFORM_FEES["ebay"])

    gross_profit = sale_price - buy_price

    # Platform fees
    commission = sale_price * fees["commission_pct"] / 100
    payment = sale_price * fees["payment_pct"] / 100
    listing = fees["listing_fee"]
    total_platform_fees = round(commission + payment + listing, 2)

    # Shipping
    shipping = custom_shipping if custom_shipping is not None else fees["avg_shipping"]

    # Risk adjustment
    risk_pct = get_risk_discount(sale_price)
    risk_amount = round(sale_price * risk_pct, 2)

    # Net profit
    net_profit = round(gross_profit - total_platform_fees - shipping - risk_amount, 2)
    roi_pct = round((net_profit / buy_price * 100), 2) if buy_price > 0 else 0.0
    margin_pct = round((net_profit / sale_price * 100), 2) if sale_price > 0 else 0.0

    return {
        "buy_price": buy_price,
        "sale_price": sale_price,
        "gross_profit": round(gross_profit, 2),
        "platform": platform,
        "platform_fees": total_platform_fees,
        "commission": round(commission, 2),
        "payment_fee": round(payment, 2),
        "shipping": round(shipping, 2),
        "risk_pct": risk_pct,
        "risk_amount": risk_amount,
        "net_profit": net_profit,
        "roi_pct": roi_pct,
        "margin_pct": margin_pct,
    }


def calculate_best_platform(buy_price: float, sale_price: float) -> dict:
    """Find the platform with the highest net profit."""
    best = None
    for platform in PLATFORM_FEES:
        result = calculate_net_profit(buy_price, sale_price, platform)
        if best is None or result["net_profit"] > best["net_profit"]:
            best = result
    return best


def format_profit_line(result: dict) -> str:
    """Format profit result as a readable line."""
    sign = "+" if result["net_profit"] >= 0 else ""
    return (
        f"{sign}{result['net_profit']}€ netto ({result['platform']}) | "
        f"ROI: {sign}{result['roi_pct']}% | "
        f"brutto: {sign}{result['gross_profit']}€ | "
        f"Gebühren: -{result['platform_fees']}€ | "
        f"Versand: -{result['shipping']}€ | "
        f"Risiko: -{result['risk_amount']}€ ({result['risk_pct']*100:.0f}%)"
    )
