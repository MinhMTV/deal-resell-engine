"""Tests for trend_predict module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from app.trend_predict import (
    predict_trend,
    get_all_trends,
    format_trend_prediction,
    format_trends_summary,
)


def _make_snapshots(prices: list[float], days_span: int = 30) -> list[dict]:
    """Generate evenly-spaced price snapshots over N days."""
    now = datetime.now(timezone.utc)
    interval = days_span / max(len(prices) - 1, 1)
    snapshots = []
    for i, price in enumerate(prices):
        ts = now - timedelta(days=days_span - i * interval)
        snapshots.append({
            "price": price,
            "source": "geizhals",
            "timestamp": ts.isoformat(),
        })
    return snapshots


def _mock_history(models: dict) -> dict:
    """Build a mock history dict. models = {name: (prices_list, last_price)}"""
    result = {}
    for name, (prices, last) in models.items():
        result[name.lower()] = {
            "snapshots": _make_snapshots(prices),
            "last_price": last,
            "all_time_low": min(prices),
            "all_time_low_at": datetime.now(timezone.utc).isoformat(),
        }
    return result


class TestPredictTrend:
    @patch("app.trend_predict._load_history")
    def test_dropping_trend(self, mock_load):
        """Prices dropping steadily over 30 days."""
        prices = [800, 790, 780, 770, 760, 750, 740, 730, 720, 710]
        mock_load.return_value = _mock_history({"galaxy s26": (prices, 710)})

        pred = predict_trend("galaxy s26", days=30)
        assert pred is not None
        assert pred["trend"] == "dropping"
        assert pred["slope_per_day"] < 0
        assert pred["predicted_price_7d"] < pred["current_price"]
        assert "Warten" in pred["recommendation"]

    @patch("app.trend_predict._load_history")
    def test_rising_trend(self, mock_load):
        """Prices rising steadily."""
        prices = [600, 610, 620, 630, 640, 650, 660, 670, 680, 690]
        mock_load.return_value = _mock_history({"iphone 16": (prices, 690)})

        pred = predict_trend("iphone 16", days=30)
        assert pred is not None
        assert pred["trend"] == "rising"
        assert pred["slope_per_day"] > 0
        assert pred["predicted_price_7d"] > pred["current_price"]
        assert "Jetzt kaufen" in pred["recommendation"]

    @patch("app.trend_predict._load_history")
    def test_stable_trend(self, mock_load):
        """Prices barely moving."""
        prices = [500, 501, 499, 500, 502, 498, 500, 501, 499, 500]
        mock_load.return_value = _mock_history({"pixel 9": (prices, 500)})

        pred = predict_trend("pixel 9", days=30)
        assert pred is not None
        assert pred["trend"] == "stable"
        assert abs(pred["slope_per_day"]) < 0.5

    @patch("app.trend_predict._load_history")
    def test_not_enough_data(self, mock_load):
        """Less than 3 snapshots → None."""
        mock_load.return_value = _mock_history({"rare model": ([999], 999)})
        assert predict_trend("rare model") is None

    @patch("app.trend_predict._load_history")
    def test_unknown_model(self, mock_load):
        mock_load.return_value = {}
        assert predict_trend("nonexistent") is None

    @patch("app.trend_predict._load_history")
    def test_high_confidence(self, mock_load):
        """Many samples + strong trend → high confidence."""
        prices = [float(800 - i * 3) for i in range(20)]
        mock_load.return_value = _mock_history({"galaxy s26 ultra": (prices, prices[-1])})

        pred = predict_trend("galaxy s26 ultra", days=30)
        assert pred["confidence"] == "high"
        assert pred["r_squared"] > 0.8


class TestGetAllTrends:
    @patch("app.trend_predict._load_history")
    def test_multiple_models(self, mock_load):
        dropping = [float(700 - i * 2) for i in range(10)]
        rising = [float(500 + i * 2) for i in range(10)]
        mock_load.return_value = {
            **_mock_history({"galaxy s26": (dropping, dropping[-1])}),
            **_mock_history({"iphone 16": (rising, rising[-1])}),
        }

        trends = get_all_trends(days=30)
        assert len(trends) == 2
        # Dropping should come first
        assert trends[0]["trend"] == "dropping"
        assert trends[1]["trend"] == "rising"

    @patch("app.trend_predict._load_history")
    def test_empty(self, mock_load):
        mock_load.return_value = {}
        assert get_all_trends() == []


class TestFormatting:
    @patch("app.trend_predict._load_history")
    def test_format_prediction(self, mock_load):
        prices = [float(800 - i * 3) for i in range(10)]
        mock_load.return_value = _mock_history({"galaxy s26": (prices, prices[-1])})

        pred = predict_trend("galaxy s26", days=30)
        text = format_trend_prediction(pred)
        assert "Galaxy S26" in text
        assert "DROPPING" in text or "dropping" in text.lower()
        assert "€" in text

    @patch("app.trend_predict._load_history")
    def test_format_summary(self, mock_load):
        dropping = [float(700 - i * 2) for i in range(10)]
        stable = [float(500 + (i % 2) * 0.5) for i in range(10)]
        mock_load.return_value = {
            **_mock_history({"galaxy s26": (dropping, dropping[-1])}),
            **_mock_history({"pixel 9": (stable, stable[-1])}),
        }

        trends = get_all_trends(days=30)
        text = format_trends_summary(trends)
        assert "Trend-Prognosen" in text
        assert "Fallend" in text
        assert "Galaxy S26" in text

    def test_format_empty(self):
        assert format_trends_summary([]) == "Keine Trend-Daten verfügbar."

    def test_format_none(self):
        assert format_trend_prediction(None) == ""
