from app.intake import _parse_markdown_deals


def test_parse_markdown_skips_image_links_and_keeps_deal_links():
    markdown = """
- ![Image 81](https://static.mydealz.de/threads/raw/ime9s/2742470_1/re/100x100/qt/60/2742470_1.jpg) [Samsung Galaxy S24 256GB für 699€](https://www.mydealz.de/deals/samsung-galaxy-s24-256gb-12345)
"""
    deals = _parse_markdown_deals(markdown, source="mydealz")

    assert len(deals) == 1
    assert deals[0]["url"].startswith("https://www.mydealz.de/deals/")
    assert "image" not in deals[0]["title"].lower()
