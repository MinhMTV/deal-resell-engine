from app.market_price import estimate_market_price, estimate_profit


def test_estimate_market_price_known_model_with_storage_bonus():
    deal = {"normalized_model": "iphone 15 pro", "normalized_storage_gb": 256}
    assert estimate_market_price(deal) == 1040.0


def test_estimate_market_price_unknown_model():
    deal = {"normalized_model": "random model", "normalized_storage_gb": 128}
    assert estimate_market_price(deal) is None


def test_estimate_profit_positive_case():
    p = estimate_profit(buy_price=699.0, market_price=900.0)
    assert p > 0
