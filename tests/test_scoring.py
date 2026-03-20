from app.scoring import score_deal


def test_phone_scores_higher_than_irrelevant_item():
    a, _ = score_deal({"title": "iPhone 16 128GB 899€", "price": 899, "votes": 80})
    b, _ = score_deal({"title": "Kaffeemaschine 29,99€", "price": 29.99, "votes": 80})
    assert a > b


def test_travel_cheap_london_with_priority_airports_scores_high():
    score, reasons = score_deal(
        {
            "title": "Direktflüge nach London ab 30€ von Wien und Frankfurt",
            "price": 30,
            "votes": 120,
        }
    )
    assert score >= 60
    assert "type=travel" in reasons
    assert "destination=london" in reasons


def test_resell_profit_signal_beats_low_margin_offer():
    high, _ = score_deal(
        {
            "title": "iPhone 15 Deal 799€ idealo 999€ Gewinn 120€",
            "price": 799,
            "votes": 40,
        }
    )
    low, _ = score_deal(
        {
            "title": "iPhone 15 Deal 949€ idealo 999€",
            "price": 949,
            "votes": 40,
        }
    )
    assert high > low
