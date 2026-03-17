from app.scoring import score_deal

def test_phone_scores_higher_than_irrelevant_item():
    a, _ = score_deal({"title": "iPhone 16 128GB 899€", "price": 899, "votes": 80})
    b, _ = score_deal({"title": "Kaffeemaschine 29,99€", "price": 29.99, "votes": 80})
    assert a > b
