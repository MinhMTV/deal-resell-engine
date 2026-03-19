from app.normalize import normalize_product


def test_normalize_iphone_line():
    row = normalize_product("Apple iPhone 15 Pro 256GB Schwarz")
    assert row["normalized_brand"] == "apple"
    assert row["normalized_model"] == "iphone 15"
    assert row["normalized_storage_gb"] == 256
    assert row["normalized_color"] == "black"


def test_normalize_tb_storage_and_pixel_model():
    row = normalize_product("Google Pixel 8 Pro 1TB Blau")
    assert row["normalized_brand"] == "google"
    assert row["normalized_model"] == "pixel 8 pro"
    assert row["normalized_storage_gb"] == 1024
    assert row["normalized_color"] == "blue"


def test_normalize_unknown_product():
    row = normalize_product("Irgendein Random Gutschein-Deal")
    assert row["normalized_brand"] is None
    assert row["normalized_model"] is None
    assert row["normalized_storage_gb"] is None
    assert row["normalized_color"] is None
