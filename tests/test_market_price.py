from app.market_price import (
    estimate_market_price,
    estimate_profit,
    StaticTableMarketPriceProvider,
    EbaySoldProvider,
    build_provider,
)


def test_estimate_market_price_known_model_with_storage_bonus():
    deal = {"normalized_model": "iphone 15 pro", "normalized_storage_gb": 256}
    assert estimate_market_price(deal) == 1040.0


def test_estimate_market_price_unknown_model():
    deal = {"normalized_model": "random model", "normalized_storage_gb": 128}
    assert estimate_market_price(deal) is None


def test_estimate_market_price_custom_provider_table():
    provider = StaticTableMarketPriceProvider(base_prices={"iphone 15 pro": 1000.0})
    deal = {"normalized_model": "iphone 15 pro", "normalized_storage_gb": 128}
    assert estimate_market_price(deal, provider=provider) == 1000.0


def test_ebay_provider_stub_returns_none():
    provider = EbaySoldProvider()
    assert provider.estimate({"normalized_model": "iphone 15 pro"}) is None


def test_estimate_market_price_default_fallback_chain_uses_static_table():
    deal = {"normalized_model": "iphone 15 pro", "normalized_storage_gb": 128}
    assert estimate_market_price(deal) == 980.0


def test_build_provider_static_mode():
    provider = build_provider("static")
    deal = {"normalized_model": "iphone 15", "normalized_storage_gb": 128}
    assert provider.estimate(deal) == 760.0


def test_build_provider_ebay_mode_returns_none_with_stub():
    provider = build_provider("ebay")
    deal = {"normalized_model": "iphone 15", "normalized_storage_gb": 128}
    assert provider.estimate(deal) is None


def test_estimate_profit_positive_case():
    p = estimate_profit(buy_price=699.0, market_price=900.0)
    assert p > 0
