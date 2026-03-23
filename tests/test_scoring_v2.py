from app.scoring_v2 import calculate_deal_score, format_score_line


def test_high_profit_deal_scores_high():
    deal = {
        "net_profit": 200.0,
        "net_roi_pct": 50.0,
        "diff": 300.0,
        "geizhals_min": 900.0,
        "deal_price": 600.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz",
        "is_contract": False,
        "is_bundle": False,
    }
    score = calculate_deal_score(deal)
    assert score["total"] >= 60
    assert score["rating"] in ["🔥 EXZELLENT", "✅ GUT"]


def test_bundle_deal_gets_penalty():
    base_deal = {
        "net_profit": 200.0,
        "net_roi_pct": 50.0,
        "diff": 300.0,
        "geizhals_min": 900.0,
        "deal_price": 600.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz",
        "is_contract": False,
        "is_bundle": False,
    }
    bundle_deal = dict(base_deal, is_bundle=True)
    base_score = calculate_deal_score(base_deal)
    bundle_score = calculate_deal_score(bundle_deal)
    assert bundle_score["total"] < base_score["total"]
    assert bundle_score["risk_penalty"] > base_score["risk_penalty"]


def test_contract_deal_gets_penalty():
    base_deal = {
        "net_profit": 100.0,
        "net_roi_pct": 20.0,
        "diff": 100.0,
        "geizhals_min": 500.0,
        "deal_price": 400.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz",
        "is_contract": False,
        "is_bundle": False,
    }
    contract_deal = dict(base_deal, is_contract=True)
    base_score = calculate_deal_score(base_deal)
    contract_score = calculate_deal_score(contract_deal)
    assert contract_score["risk_penalty"] > base_score["risk_penalty"]


def test_no_geizhals_link_reduces_reliability():
    with_link = {
        "net_profit": 100.0, "net_roi_pct": 20.0, "diff": 100.0,
        "geizhals_min": 500.0, "deal_price": 400.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz", "is_contract": False, "is_bundle": False,
    }
    without_link = dict(with_link, geizhals_link=None)
    assert calculate_deal_score(with_link)["reliability"] > calculate_deal_score(without_link)["reliability"]


def test_high_diff_scores_higher():
    low_diff = {
        "net_profit": 50.0, "net_roi_pct": 10.0, "diff": 25.0,
        "geizhals_min": 500.0, "deal_price": 475.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz", "is_contract": False, "is_bundle": False,
    }
    high_diff = dict(low_diff, diff=400.0, deal_price=100.0)
    assert calculate_deal_score(high_diff)["market_position"] > calculate_deal_score(low_diff)["market_position"]


def test_score_never_negative():
    deal = {
        "net_profit": -100.0, "net_roi_pct": -20.0, "diff": 10.0,
        "geizhals_min": 100.0, "deal_price": 90.0,
        "geizhals_link": None, "source": "unknown",
        "is_contract": True, "is_bundle": True,
    }
    score = calculate_deal_score(deal)
    assert score["total"] >= 0


def test_score_capped_at_100():
    deal = {
        "net_profit": 10000.0, "net_roi_pct": 500.0, "diff": 5000.0,
        "geizhals_min": 10000.0, "deal_price": 5000.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz", "is_contract": False, "is_bundle": False,
    }
    score = calculate_deal_score(deal)
    assert score["total"] <= 100


def test_format_score_line():
    deal = {
        "net_profit": 200.0, "net_roi_pct": 50.0, "diff": 300.0,
        "geizhals_min": 900.0, "deal_price": 600.0,
        "geizhals_link": "https://geizhals.de/test.html",
        "source": "mydealz", "is_contract": False, "is_bundle": False,
    }
    score = calculate_deal_score(deal)
    line = format_score_line(score)
    assert "Score:" in line
    assert "Profit:" in line
