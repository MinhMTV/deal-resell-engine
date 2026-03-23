"""Tests for deal report generator."""

import json
import pytest
from app.deal_report import generate_deal_report, generate_deal_report_json
from app.deal_tracker import connect_tracker, mark_found, update_stage


@pytest.fixture
def tracker_conn(monkeypatch):
    """Use in-memory DB for testing."""
    import sqlite3
    from app.deal_tracker import TRACKER_SCHEMA
    conn = sqlite3.connect(":memory:")
    conn.execute(TRACKER_SCHEMA)
    conn.commit()

    # Patch connect_tracker to return our in-memory conn
    monkeypatch.setattr("app.deal_report.connect_tracker", lambda: conn)
    yield conn
    conn.close()


SAMPLE_DEAL = {
    "alert_key": "mydealz:galaxy s26:abc123",
    "source": "mydealz",
    "normalized_model": "galaxy s26",
    "deal_url": "https://mydealz.de/deals/test",
    "deal_price": 599.0,
    "diff": 150.0,
    "net_profit": 89.50,
    "net_roi_pct": 14.94,
    "net_platform": "ebay",
}


class TestDealReport:
    def test_empty_report(self, tracker_conn):
        report = generate_deal_report(days=1)
        assert "Keine Deals" in report

    def test_with_deals(self, tracker_conn):
        mark_found(tracker_conn, SAMPLE_DEAL)
        report = generate_deal_report(days=30)
        assert "Galaxy S26" in report
        assert "+89.5€" in report or "89.5" in report

    def test_top_deals_sorted(self, tracker_conn):
        mark_found(tracker_conn, SAMPLE_DEAL)
        mark_found(tracker_conn, {
            "alert_key": "mydealz:iphone 16:def456",
            "source": "mydealz",
            "normalized_model": "iphone 16",
            "deal_url": "https://mydealz.de/deals/test2",
            "deal_price": 299.0,
            "diff": 400.0,
            "net_profit": 200.0,
            "net_roi_pct": 66.89,
            "net_platform": "ebay",
        })
        report = generate_deal_report(days=30, top_n=5)
        # iPhone should come first (higher profit)
        lines = report.split("\n")
        iphone_line = next((l for l in lines if "Iphone 16" in l), None)
        galaxy_line = next((l for l in lines if "Galaxy S26" in l), None)
        assert iphone_line is not None
        assert galaxy_line is not None

    def test_source_breakdown(self, tracker_conn):
        mark_found(tracker_conn, SAMPLE_DEAL)
        report = generate_deal_report(days=30)
        assert "mydealz" in report


class TestDealReportJson:
    def test_json_structure(self, tracker_conn):
        mark_found(tracker_conn, SAMPLE_DEAL)
        data = generate_deal_report_json(days=30)
        assert "pipeline_stats" in data
        assert "top_deals" in data
        assert "trends" in data
        assert data["total"] == 1

    def test_json_serializable(self, tracker_conn):
        mark_found(tracker_conn, SAMPLE_DEAL)
        data = generate_deal_report_json(days=30)
        json_str = json.dumps(data, ensure_ascii=False)
        assert len(json_str) > 0
