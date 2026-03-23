"""Tests for daily_summary module."""

from unittest.mock import patch
from app.daily_summary import generate_daily_summary, generate_daily_summary_json


class TestDailySummary:
    @patch("app.daily_summary.get_pipeline_stats")
    @patch("app.daily_summary.connect_tracker")
    @patch("app.daily_summary.get_all_tracked")
    @patch("app.daily_summary.get_all_trends")
    def test_generates_text(self, mock_trends, mock_tracked, mock_connect, mock_pipeline):
        mock_trends.return_value = []
        mock_tracked.return_value = []
        mock_pipeline.return_value = {"total_found": 0, "stages": {}, "conversion": {}, "best_deals": []}

        text = generate_daily_summary()
        assert "Tagesbericht" in text
        assert "System" in text

    @patch("app.daily_summary.get_pipeline_stats")
    @patch("app.daily_summary.connect_tracker")
    @patch("app.daily_summary.get_all_tracked")
    @patch("app.daily_summary.get_all_trends")
    def test_with_hits(self, mock_trends, mock_tracked, mock_connect, mock_pipeline):
        mock_trends.return_value = []
        mock_tracked.return_value = []
        mock_pipeline.return_value = {"total_found": 0, "stages": {}, "conversion": {}, "best_deals": []}

        hits = [{"normalized_model": "galaxy s26", "diff": 100, "net_profit": 50}]
        text = generate_daily_summary(hits=hits)
        assert "Galaxy S26" in text
        assert "+100€" in text

    @patch("app.daily_summary.get_pipeline_stats")
    @patch("app.daily_summary.connect_tracker")
    @patch("app.daily_summary.get_all_tracked")
    @patch("app.daily_summary.get_all_trends")
    def test_json_output(self, mock_trends, mock_tracked, mock_connect, mock_pipeline):
        mock_trends.return_value = []
        mock_tracked.return_value = []
        mock_pipeline.return_value = {"total_found": 0, "stages": {}, "conversion": {}, "best_deals": []}

        data = generate_daily_summary_json()
        assert "trends" in data
        assert "pipeline" in data
        assert "system_health" in data
        assert data["system_health"]["tracked_models"] == 0
