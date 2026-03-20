from app.normalize import normalize_product


def test_normalize_iphone_line():
    row = normalize_product("Apple iPhone 15 Pro 256GB Schwarz")
    assert row["normalized_brand"] == "apple"
    assert row["normalized_model"] == "iphone 15 pro"
    assert row["normalized_storage_gb"] == 256
    assert row["normalized_color"] == "black"


def test_normalize_tb_storage_and_pixel_model():
    row = normalize_product("Google Pixel 8 Pro 1TB Blau")
    assert row["normalized_brand"] == "google"
    assert row["normalized_model"] == "pixel 8 pro"
    assert row["normalized_storage_gb"] == 1024
    assert row["normalized_color"] == "blue"


def test_normalize_iphone_variant_pro_max():
    row = normalize_product("Apple iPhone 15 Pro Max 512GB Weiß")
    assert row["normalized_brand"] == "apple"
    assert row["normalized_model"] == "iphone 15 pro max"
    assert row["normalized_storage_gb"] == 512
    assert row["normalized_color"] == "white"


def test_normalize_galaxy_ultra_variant():
    row = normalize_product("Samsung Galaxy S24 Ultra 256GB Titanium Schwarz")
    assert row["normalized_brand"] == "samsung"
    assert row["normalized_model"] == "galaxy s24 ultra"
    assert row["normalized_storage_gb"] == 256
    assert row["normalized_color"] == "black"


def test_normalize_prefers_storage_over_ram_capacity():
    row = normalize_product("Lenovo ThinkPad 16GB RAM 512GB SSD")
    assert row["normalized_storage_gb"] == 512


def test_normalize_handles_multiple_storage_mentions():
    row = normalize_product("PS5 Bundle 825GB + externe SSD 1TB")
    assert row["normalized_storage_gb"] == 1024


def test_normalize_macbook_chip_variant():
    row = normalize_product("Apple MacBook Air 13 M4 16GB 256GB Himmelblau")
    assert row["normalized_model"] == "macbook air m4"
    assert row["normalized_storage_gb"] == 256


def test_normalize_unknown_product():
    row = normalize_product("Irgendein Random Gutschein-Deal")
    assert row["normalized_brand"] is None
    assert row["normalized_model"] is None
    assert row["normalized_storage_gb"] is None
    assert row["normalized_color"] is None
