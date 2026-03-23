from app.profit import calculate_net_profit, calculate_best_platform, format_profit_line


def test_ebay_profit_basic():
    r = calculate_net_profit(buy_price=500.0, sale_price=800.0, platform="ebay")
    assert r["buy_price"] == 500.0
    assert r["sale_price"] == 800.0
    assert r["gross_profit"] == 300.0
    assert r["platform"] == "ebay"
    # eBay: 12.5% commission + 2.49% payment + 5.99 shipping + 2% risk
    assert r["platform_fees"] > 0
    assert r["net_profit"] < 300.0  # after fees
    assert r["net_profit"] > 100.0  # still profitable after all deductions
    assert r["roi_pct"] > 0


def test_kleinanzeigen_profit_better_than_ebay():
    ebay = calculate_net_profit(500.0, 800.0, "ebay")
    kleinanzeigen = calculate_net_profit(500.0, 800.0, "kleinanzeigen")
    assert kleinanzeigen["net_profit"] > ebay["net_profit"]


def test_local_profit_no_fees():
    r = calculate_net_profit(500.0, 800.0, "local")
    assert r["platform_fees"] == 0.0
    assert r["shipping"] == 0.0
    assert r["net_profit"] > 280.0  # only risk discount


def test_negative_profit():
    r = calculate_net_profit(buy_price=800.0, sale_price=700.0, platform="ebay")
    assert r["net_profit"] < 0
    assert r["roi_pct"] < 0


def test_risk_discount_increases_with_price():
    low = calculate_net_profit(100.0, 200.0, "local")
    high = calculate_net_profit(100.0, 2000.0, "local")
    assert high["risk_pct"] > low["risk_pct"]


def test_calculate_best_platform():
    best = calculate_best_platform(500.0, 800.0)
    assert best["platform"] == "local"  # 0% fees
    assert best["net_profit"] > 0


def test_format_profit_line():
    r = calculate_net_profit(500.0, 800.0, "ebay")
    line = format_profit_line(r)
    assert "+2" in line or "+1" in line  # positive profit
    assert "ebay" in line
    assert "ROI" in line


def test_custom_shipping():
    default = calculate_net_profit(500.0, 800.0, "ebay")
    free_ship = calculate_net_profit(500.0, 800.0, "ebay", custom_shipping=0.0)
    assert free_ship["net_profit"] > default["net_profit"]
    assert free_ship["shipping"] == 0.0
