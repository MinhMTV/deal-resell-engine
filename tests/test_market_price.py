import app.market_price as mp
from app.market_price import (
    estimate_market_price,
    estimate_profit,
    StaticTableMarketPriceProvider,
    EbaySoldProvider,
    GeizhalsProvider,
    build_provider,
    _extract_eur_prices,
    _query_variants_from_deal,
    _extract_variant_rows,
    _cluster_prices,
    _model_aliases,
    _is_accessory_url,
    _passes_brand_guard,
    _extract_geizhals_product_url,
)


def test_estimate_market_price_known_model_with_storage_bonus():
    deal = {"normalized_model": "iphone 15 pro", "normalized_storage_gb": 256}
    assert estimate_market_price(deal, provider=StaticTableMarketPriceProvider()) == 1040.0


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


def test_estimate_market_price_default_fallback_chain_uses_static_table(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(mp.requests, "get", _boom)
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


def test_build_provider_geizhals_mode():
    provider = build_provider("geizhals")
    assert isinstance(provider, GeizhalsProvider)


def test_extract_eur_prices_parses_common_formats():
    text = "Bestpreis 1.099,00 € statt 1299€ und gebraucht 899,50 €"
    prices = _extract_eur_prices(text)
    assert 1099.0 in prices
    assert 1299.0 in prices
    assert 899.5 in prices


def test_query_variants_prefer_exact_storage_variant():
    variants = _query_variants_from_deal({"normalized_model": "galaxy s24 ultra", "normalized_storage_gb": 256})
    assert variants[0] == "galaxy s24 ultra 256gb"
    assert "galaxy s24 ultra 256" in variants
    assert "galaxy s24 ultra" in variants


def test_query_variants_without_storage_use_model_only():
    variants = _query_variants_from_deal({"normalized_model": "galaxy s24 ultra", "normalized_storage_gb": None})
    assert variants == ["galaxy s24 ultra"]


def test_extract_variant_rows_filters_model_and_storage():
    text = """
ab [€ 745,00](https://geizhals.de/samsung-galaxy-s24-ultra-s928b-ds-256gb-titanium-gray-a3105415.html#offerlist)
ab [€ 749,00](https://geizhals.de/samsung-galaxy-s24-ultra-s928b-ds-256gb-titanium-violet-a3105426.html#offerlist)
ab [€ 699,00](https://geizhals.de/samsung-galaxy-s24-s921b-ds-256gb-black-a3105000.html#offerlist)
"""
    rows = _extract_variant_rows(text, model="galaxy s24 ultra", storage_gb=256)
    assert len(rows) == 2
    prices = sorted(r["price"] for r in rows)
    assert prices == [745.0, 749.0]


def test_model_aliases_include_plus_and_model_code_tokens():
    aliases = _model_aliases("galaxy s24 plus")
    assert "s24+" in aliases
    assert "s926" in aliases


def test_cluster_prices_separates_outliers_by_100_eur():
    rows = [
        {"price": 745.0, "url": "a"},
        {"price": 749.0, "url": "b"},
        {"price": 824.68, "url": "c"},
        {"price": 1137.97, "url": "d"},
    ]
    inliers, outliers, min_price, next_price, gap = _cluster_prices(rows, max_deviation_eur=100.0)
    assert min_price == 745.0
    assert next_price == 749.0
    assert gap == 4.0
    assert len(inliers) == 3
    assert len(outliers) == 1
    assert outliers[0]["price"] == 1137.97


def test_estimate_profit_positive_case():
    p = estimate_profit(buy_price=699.0, market_price=900.0)
    assert p > 0


# ── Accessory & Brand Guard Tests ──────────────────────────────────────────


def test_is_accessory_url_detects_common_keywords():
    assert _is_accessory_url("https://geizhals.de/spigen-case-a123.html") is True
    assert _is_accessory_url("https://geizhals.de/huelle-fuer-iphone-a123.html") is True
    assert _is_accessory_url("https://geizhals.de/schutzglas-a123.html") is True
    assert _is_accessory_url("https://geizhals.de/ladekabel-a123.html") is True
    assert _is_accessory_url("https://geizhals.de/faltschloss-airtag-a123.html") is True
    assert _is_accessory_url("https://geizhals.de/armband-apple-watch-a123.html") is True
    assert _is_accessory_url("https://geizhals.de/apple-iphone-16-pro-a123.html") is False
    assert _is_accessory_url("https://geizhals.de/samsung-galaxy-s25-ultra-a123.html") is False


def test_passes_brand_guard_apple_products():
    # AirTag must have 'apple' in URL
    assert _passes_brand_guard("https://geizhals.de/apple-airtag-a123.html", "airtag") is True
    assert _passes_brand_guard("https://geizhals.de/trelock-airtag-faltschloss-a123.html", "airtag") is False
    # iPhone
    assert _passes_brand_guard("https://geizhals.de/apple-iphone-16-a123.html", "iphone 16") is True
    assert _passes_brand_guard("https://geizhals.de/no-name-iphone-huelle-a123.html", "iphone 16") is False
    # AirPods
    assert _passes_brand_guard("https://geizhals.de/apple-airpods-pro-2-a123.html", "airpods pro") is True
    assert _passes_brand_guard("https://geizhals.de/cheap-airpods-knockoff-a123.html", "airpods pro") is False


def test_passes_brand_guard_samsung_products():
    assert _passes_brand_guard("https://geizhals.de/samsung-galaxy-s25-a123.html", "galaxy s25") is True
    assert _passes_brand_guard("https://geizhals.de/fake-galaxy-case-a123.html", "galaxy s25") is False


def test_passes_brand_guard_pixel_products():
    assert _passes_brand_guard("https://geizhals.de/google-pixel-9-a123.html", "pixel 9") is True
    assert _passes_brand_guard("https://geizhals.de/fake-pixel-cover-a123.html", "pixel 9") is False


def test_passes_brand_guard_no_guard_for_unmapped_models():
    # Models without brand guard entry should always pass
    assert _passes_brand_guard("https://geizhals.de/anything-a123.html", "kindle paperwhite") is True
    assert _passes_brand_guard("https://geizhals.de/anything-a123.html", "legion go") is True
    # Models WITH guard — must match expected brand
    assert _passes_brand_guard("https://geizhals.de/apple-macbook-air-m5-a123.html", "macbook air m5") is True
    assert _passes_brand_guard("https://geizhals.de/fake-macbook-a123.html", "macbook air m5") is False
    assert _passes_brand_guard("https://geizhals.de/valve-steam-deck-oled-a123.html", "steam deck") is True
    assert _passes_brand_guard("https://geizhals.de/fake-handheld-a123.html", "steam deck") is False


def test_extract_variant_rows_filters_accessories_and_brand_mismatches():
    text = """
ab [€ 89,99](https://geizhals.de/apple-airtag-4er-pack-a2345456.html#offerlist)
ab [€ 55,95](https://geizhals.de/trelock-fs-480-airtag-faltschloss-a3438786.html#offerlist)
ab [€ 12,99](https://geizhals.de/cheap-airtag-case-silikon-a9999.html#offerlist)
"""
    rows = _extract_variant_rows(text, model="airtag", storage_gb=None)
    assert len(rows) == 1
    assert "apple" in rows[0]["url"]
    assert rows[0]["price"] == 89.99


# ── Geizhals Product URL Extraction ────────────────────────────────────────


def test_extract_geizhals_product_url_finds_best_match():
    text = """
[Apple iPad Air 7 256GB](https://geizhals.de/apple-ipad-air-7-2025-m3-256gb-wlan-a3745123.html)
[Samsung Galaxy Tab](https://geizhals.de/samsung-galaxy-tab-s10-a3588000.html)
"""
    url = _extract_geizhals_product_url(text, "ipad air 7")
    assert url is not None
    assert "ipad-air-7" in url


def test_extract_geizhals_product_url_no_false_match():
    text = """
[Apple iPad Air 7](https://geizhals.de/apple-ipad-air-7-2025-m3-a3745123.html)
"""
    url = _extract_geizhals_product_url(text, "macbook air m5")
    assert url is None


def test_extract_geizhals_product_url_empty_text():
    assert _extract_geizhals_product_url("", "iphone 16") is None
    assert _extract_geizhals_product_url("no urls here", "iphone 16") is None
