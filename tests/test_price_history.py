import os
import json
from pathlib import Path
from app.price_history import log_price, get_price_stats, get_all_tracked, format_price_trend, HISTORY_PATH


def setup_function():
    # Clean history before each test
    if HISTORY_PATH.exists():
        HISTORY_PATH.unlink()


def teardown_function():
    if HISTORY_PATH.exists():
        HISTORY_PATH.unlink()


def test_log_price_creates_entry():
    log_price("galaxy s26", 989.0, source="geizhals")
    stats = get_price_stats("galaxy s26")
    assert stats is not None
    assert stats["current"] == 989.0
    assert stats["all_time_low"] == 989.0
    assert stats["samples"] == 1


def test_log_price_updates_all_time_low():
    log_price("galaxy s26", 1000.0)
    log_price("galaxy s26", 950.0)
    log_price("galaxy s26", 980.0)
    stats = get_price_stats("galaxy s26")
    assert stats["all_time_low"] == 950.0
    assert stats["current"] == 980.0
    assert stats["samples"] == 3


def test_log_price_case_insensitive():
    log_price("Galaxy S26", 989.0)
    stats = get_price_stats("galaxy s26")
    assert stats is not None
    assert stats["current"] == 989.0


def test_get_price_stats_no_history():
    assert get_price_stats("nonexistent model") is None


def test_get_price_stats_period_stats():
    log_price("iphone 16", 800.0)
    log_price("iphone 16", 820.0)
    log_price("iphone 16", 780.0)
    stats = get_price_stats("iphone 16", days=7)
    assert stats["period_low"] == 780.0
    assert stats["period_high"] == 820.0
    assert stats["period_avg"] == 800.0
    assert stats["drop_from_high"] == 40.0  # 820 - 780 (current)


def test_get_all_tracked_returns_sorted():
    log_price("model_a", 100.0)
    log_price("model_a", 90.0)
    log_price("model_b", 500.0)
    tracked = get_all_tracked()
    assert len(tracked) == 2
    # model_a has 10€ drop, model_b has 0€ drop
    assert tracked[0]["model"] == "model_a"


def test_format_price_trend():
    log_price("galaxy s26", 989.0)
    stats = get_price_stats("galaxy s26")
    line = format_price_trend(stats)
    assert "Galaxy S26" in line
    assert "989" in line
    assert "Allzeittief" in line


def test_format_price_trend_with_drop():
    log_price("pixel 10", 700.0)
    log_price("pixel 10", 650.0)
    stats = get_price_stats("pixel 10")
    line = format_price_trend(stats)
    assert "-50" in line
