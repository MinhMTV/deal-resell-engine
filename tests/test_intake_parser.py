from app.intake import _parse_markdown_deals, detect_contract_deal, detect_bundle_deal


def test_parse_markdown_skips_image_links_and_keeps_deal_links():
    markdown = """
- ![Image 81](https://static.mydealz.de/threads/raw/ime9s/2742470_1/re/100x100/qt/60/2742470_1.jpg) [Samsung Galaxy S24 256GB für 699€](https://www.mydealz.de/deals/samsung-galaxy-s24-256gb-12345)
"""
    deals, stop_hit = _parse_markdown_deals(markdown, source="mydealz")

    assert stop_hit is False
    assert len(deals) == 1
    assert deals[0]["url"].startswith("https://www.mydealz.de/deals/")
    assert "image" not in deals[0]["title"].lower()


def test_detect_contract_deal_extracts_monthly_and_upfront():
    deal = {
        "title": "Samsung Galaxy S25 FE 128GB | 9,99€/Monat & 199€ Zuzahlung",
        "price": 90.0,
    }
    result = detect_contract_deal(deal)
    assert result["is_contract"] is True
    assert result["contract_monthly"] == 9.99
    assert result["contract_upfront"] == 199.0
    assert result["contract_months"] == 24
    assert result["contract_total"] == 438.76


def test_detect_contract_deal_monthly_only():
    deal = {
        "title": "Allnet Flat 30GB für 14,82€/Monat",
        "price": 14.82,
    }
    result = detect_contract_deal(deal)
    assert result["is_contract"] is True
    assert result["contract_monthly"] == 14.82
    assert result["contract_upfront"] is None
    assert result["contract_total"] == 355.68


def test_detect_contract_deal_not_a_contract():
    deal = {"title": "Samsung Galaxy S26 für 899€", "price": 899.0}
    result = detect_contract_deal(deal)
    assert result["is_contract"] is False


def test_detect_bundle_deal_with_bundle_keyword():
    deal = {"title": "Samsung Galaxy S26 im Bundle mit Galaxy Buds", "price": 899.0}
    result = detect_bundle_deal(deal)
    assert result["is_bundle"] is True
    assert "bundle" in result["bundle_reason"]


def test_detect_bundle_deal_with_eintausch():
    deal = {"title": "Pixel 10 mit 100€ Eintauschbonus", "price": 100.0}
    result = detect_bundle_deal(deal)
    assert result["is_bundle"] is True
    assert "eintausch" in result["bundle_reason"]


def test_detect_bundle_deal_with_cashback():
    deal = {"title": "AirPods 3 Pro | 10% Cashback", "price": 182.28}
    result = detect_bundle_deal(deal)
    assert result["is_bundle"] is True
    assert "cashback" in result["bundle_reason"]


def test_detect_bundle_deal_not_a_bundle():
    deal = {"title": "Samsung Galaxy S26 512GB für 899€", "price": 899.0}
    result = detect_bundle_deal(deal)
    assert result["is_bundle"] is False
