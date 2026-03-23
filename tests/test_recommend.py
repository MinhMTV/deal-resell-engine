from app.recommend import score_recommendation, format_recommendation


def test_high_profit_deal():
    deal = {
        "normalized_model": "galaxy s26",
        "deal_price": 700.0,
        "geizhals_min": 989.0,
        "diff": 289.0,
        "is_contract": False,
        "is_bundle": False,
        "net_profit": 200.0,
        "net_roi_pct": 28.0,
    }
    rec = score_recommendation(deal)
    assert rec["score"] >= 40
    assert "KAUFEN" in rec["recommendation"] or "BETRACHT" in rec["recommendation"]


def test_contract_deal_penalty():
    deal = {
        "normalized_model": "galaxy s25 fe",
        "deal_price": 438.76,
        "geizhals_min": 468.9,
        "diff": 30.14,
        "is_contract": True,
        "is_bundle": False,
    }
    rec = score_recommendation(deal)
    assert "Vertrag" in str(rec["reasons"])


def test_bundle_deal_penalty():
    deal = {
        "normalized_model": "pixel 10",
        "deal_price": 100.0,
        "geizhals_min": 663.0,
        "diff": 563.0,
        "is_contract": False,
        "is_bundle": True,
    }
    rec = score_recommendation(deal)
    assert "Bundle" in str(rec["reasons"])


def test_unrealistic_ratio():
    deal = {
        "normalized_model": "galaxy s26",
        "deal_price": 100.0,
        "geizhals_min": 989.0,
        "diff": 889.0,
        "is_contract": False,
        "is_bundle": True,
    }
    rec = score_recommendation(deal)
    # Ratio > 5, should have penalty
    assert any("Unrealistisch" in r for r in rec["reasons"])


def test_low_margin_deal():
    deal = {
        "normalized_model": "dji neo",
        "deal_price": 113.04,
        "geizhals_min": 142.99,
        "diff": 29.95,
        "is_contract": False,
        "is_bundle": False,
    }
    rec = score_recommendation(deal)
    assert rec["score"] < 50


def test_format_recommendation():
    rec = {
        "score": 75.0,
        "recommendation": "🟢 KAUFEN",
        "reasons": ["💰 Hoher Gewinn: +200€", "🔥 Mega-Differenz"],
    }
    line = format_recommendation(rec)
    assert "KAUFEN" in line
    assert "75" in line


def test_empty_deal():
    deal = {}
    rec = score_recommendation(deal)
    assert rec["score"] == 0
    assert "ÜBERSPRINGEN" in rec["recommendation"]
