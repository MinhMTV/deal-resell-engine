"""Tests for url_health module."""

import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from app.url_health import check_url, check_pipeline_urls, format_health_report
from app.deal_tracker import connect_tracker, mark_found


SAMPLE_HIT = {
    "alert_key": "mydealz:galaxy s26:abc123",
    "source": "mydealz",
    "normalized_model": "galaxy s26",
    "deal_url": "https://mydealz.de/deals/test-123",
    "deal_price": 599.0,
    "diff": 150.0,
    "net_profit": 89.50,
    "net_roi_pct": 14.94,
    "net_platform": "ebay",
}


@pytest.fixture
def tracker_conn():
    conn = sqlite3.connect(":memory:")
    from app.deal_tracker import TRACKER_SCHEMA
    conn.execute(TRACKER_SCHEMA)
    conn.commit()
    yield conn
    conn.close()


class TestCheckUrl:
    @patch("app.url_health.requests")
    def test_live_url(self, mock_requests):
        resp = MagicMock()
        resp.status_code = 200
        resp.url = "https://example.com/deal"
        mock_requests.head.return_value = resp

        result = check_url("https://example.com/deal")
        assert result["status"] == "live"
        assert result["http_code"] == 200

    @patch("app.url_health.requests")
    def test_expired_404(self, mock_requests):
        resp = MagicMock()
        resp.status_code = 404
        resp.url = "https://example.com/dead"
        mock_requests.head.return_value = resp

        result = check_url("https://example.com/dead")
        assert result["status"] == "expired"
        assert result["http_code"] == 404

    @patch("app.url_health.requests")
    def test_expired_500(self, mock_requests):
        resp = MagicMock()
        resp.status_code = 500
        resp.url = "https://example.com/broken"
        mock_requests.head.return_value = resp

        result = check_url("https://example.com/broken")
        assert result["status"] == "expired"

    @patch("app.url_health.requests")
    def test_timeout(self, mock_requests):
        import requests as real_requests
        mock_requests.Timeout = real_requests.Timeout
        mock_requests.head.side_effect = real_requests.Timeout("Connection timed out")

        result = check_url("https://example.com/slow")
        assert result["status"] == "error"
        assert result["error"] == "timeout"

    @patch("app.url_health.requests")
    def test_connection_error(self, mock_requests):
        import requests as real_requests
        mock_requests.ConnectionError = real_requests.ConnectionError
        mock_requests.Timeout = real_requests.Timeout
        mock_requests.head.side_effect = real_requests.ConnectionError("DNS failed")

        result = check_url("https://example.com/bad")
        assert result["status"] == "error"
        assert "DNS failed" in result["error"]


class TestFormatHealthReport:
    def test_empty(self):
        health = {"total": 0, "live": 0, "expired": 0, "error": 0, "details": []}
        text = format_health_report(health)
        assert "Keine Deals" in text

    def test_all_live(self):
        health = {
            "total": 3,
            "live": 3,
            "expired": 0,
            "error": 0,
            "details": [
                {"status": "live", "model": "galaxy s26", "url": "https://example.com/1"},
            ],
        }
        text = format_health_report(health)
        assert "✅ Live: 3" in text
        assert "❌ Expired: 0" in text

    def test_with_expired(self):
        health = {
            "total": 2,
            "live": 1,
            "expired": 1,
            "error": 0,
            "details": [
                {"status": "live", "model": "galaxy s26", "url": "https://example.com/1"},
                {"status": "expired", "model": "iphone 16", "url": "https://example.com/dead", "http_code": 404},
            ],
        }
        text = format_health_report(health)
        assert "Abgelaufene Deals" in text
        assert "Iphone 16" in text
        assert "HTTP 404" in text
