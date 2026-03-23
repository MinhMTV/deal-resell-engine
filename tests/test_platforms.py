from app.platforms import _extract_amazon_price, compare_platforms, format_comparison


def test_extract_amazon_price_eur_format():
    text = "Samsung Galaxy S26 für €899,00 bei Amazon"
    assert _extract_amazon_price(text) == 899.0


def test_extract_amazon_price_reversed():
    text = "Preis: 1029,00€ bei Amazon.de"
    assert _extract_amazon_price(text) == 1029.0


def test_extract_amazon_price_no_match():
    assert _extract_amazon_price("Kein Preis verfügbar") is None


def test_extract_amazon_price_filters_low():
    text = "Versand: €4,99 | Preis: €899,00"
    assert _extract_amazon_price(text) == 899.0


def test_compare_platforms_geizhals_only():
    result = compare_platforms(500.0, 800.0, None)
    assert result["best"]["platform"] == "geizhals"
    assert result["best"]["diff"] == 300.0


def test_compare_platforms_amazon_better():
    result = compare_platforms(500.0, 600.0, 750.0)
    assert result["best"]["platform"] == "amazon"
    assert result["best"]["diff"] == 250.0


def test_compare_platforms_both():
    result = compare_platforms(500.0, 800.0, 700.0)
    assert "geizhals" in result["comparisons"]
    assert "amazon" in result["comparisons"]


def test_format_comparison():
    result = compare_platforms(500.0, 800.0, 700.0)
    line = format_comparison(result)
    assert "geizhals" in line
    assert "amazon" in line
    assert "+300" in line
    assert "+200" in line


def test_compare_savings_pct():
    result = compare_platforms(500.0, 1000.0, None)
    assert result["comparisons"]["geizhals"]["savings_pct"] == 50.0
