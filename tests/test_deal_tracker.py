"""Tests for deal_tracker module."""

import sqlite3
import pytest
from app.deal_tracker import (
    connect_tracker,
    mark_found,
    update_stage,
    get_deal,
    list_deals,
    get_pipeline_stats,
    format_pipeline_stats,
    format_deal_detail,
)


@pytest.fixture
def conn():
    """In-memory SQLite connection for testing."""
    conn = sqlite3.connect(":memory:")
    from app.deal_tracker import TRACKER_SCHEMA
    conn.execute(TRACKER_SCHEMA)
    conn.commit()
    yield conn
    conn.close()


SAMPLE_HIT = {
    "alert_key": "mydealz:galaxy s26:abc123",
    "source": "mydealz",
    "normalized_model": "galaxy s26",
    "normalized_storage_gb": 256,
    "deal_url": "https://mydealz.de/deals/test-123",
    "deal_price": 599.0,
    "effective_price": 599.0,
    "geizhals_min": 749.0,
    "geizhals_link": "https://geizhals.de/test",
    "diff": 150.0,
    "net_profit": 89.50,
    "net_roi_pct": 14.94,
    "net_platform": "ebay",
    "is_contract": False,
    "is_bundle": False,
}


SAMPLE_CONTRACT_HIT = {
    "alert_key": "preisjaeger:iphone 16:def456",
    "source": "preisjaeger",
    "normalized_model": "iphone 16",
    "normalized_storage_gb": 128,
    "deal_url": "https://preisjaeger.at/deals/test-456",
    "deal_price": 29.99,
    "effective_price": 509.99,
    "geizhals_min": 699.0,
    "geizhals_link": "https://geizhals.de/test2",
    "diff": 189.01,
    "net_profit": 112.30,
    "net_roi_pct": 22.02,
    "net_platform": "ebay",
    "is_contract": True,
    "is_bundle": False,
}


class TestMarkFound:
    def test_new_deal(self, conn):
        assert mark_found(conn, SAMPLE_HIT) is True
        deal = get_deal(conn, "mydealz:galaxy s26:abc123")
        assert deal is not None
        assert deal["normalized_model"] == "galaxy s26"
        assert deal["stage"] == "found"
        assert deal["deal_price"] == 599.0
        assert deal["diff"] == 150.0

    def test_duplicate(self, conn):
        assert mark_found(conn, SAMPLE_HIT) is True
        assert mark_found(conn, SAMPLE_HIT) is False

    def test_contract_deal(self, conn):
        assert mark_found(conn, SAMPLE_CONTRACT_HIT) is True
        deal = get_deal(conn, "preisjaeger:iphone 16:def456")
        assert deal["is_contract"] == 1
        assert deal["effective_price"] == 509.99


class TestUpdateStage:
    def test_advance_stages(self, conn):
        mark_found(conn, SAMPLE_HIT)

        assert update_stage(conn, "mydealz:galaxy s26:abc123", "compared") is True
        deal = get_deal(conn, "mydealz:galaxy s26:abc123")
        assert deal["stage"] == "compared"
        assert deal["compared_at"] is not None

        assert update_stage(conn, "mydealz:galaxy s26:abc123", "notified") is True
        deal = get_deal(conn, "mydealz:galaxy s26:abc123")
        assert deal["stage"] == "notified"
        assert deal["notified_at"] is not None

    def test_bought_with_notes(self, conn):
        mark_found(conn, SAMPLE_HIT)
        update_stage(conn, "mydealz:galaxy s26:abc123", "bought", notes="Ordered via Amazon")
        deal = get_deal(conn, "mydealz:galaxy s26:abc123")
        assert deal["stage"] == "bought"
        assert deal["notes"] == "Ordered via Amazon"

    def test_sold_with_price(self, conn):
        mark_found(conn, SAMPLE_HIT)
        update_stage(conn, "mydealz:galaxy s26:abc123", "bought")
        update_stage(conn, "mydealz:galaxy s26:abc123", "sold", sold_price=680.0)
        deal = get_deal(conn, "mydealz:galaxy s26:abc123")
        assert deal["stage"] == "sold"
        assert deal["sold_price"] == 680.0

    def test_invalid_stage(self, conn):
        mark_found(conn, SAMPLE_HIT)
        with pytest.raises(ValueError):
            update_stage(conn, "mydealz:galaxy s26:abc123", "invalid")

    def test_nonexistent_key(self, conn):
        assert update_stage(conn, "nonexistent:key:123", "compared") is False


class TestListDeals:
    def test_list_all(self, conn):
        mark_found(conn, SAMPLE_HIT)
        mark_found(conn, SAMPLE_CONTRACT_HIT)
        deals = list_deals(conn)
        assert len(deals) == 2

    def test_filter_by_stage(self, conn):
        mark_found(conn, SAMPLE_HIT)
        mark_found(conn, SAMPLE_CONTRACT_HIT)
        update_stage(conn, "mydealz:galaxy s26:abc123", "notified")

        found = list_deals(conn, stage="found")
        notified = list_deals(conn, stage="notified")
        assert len(found) == 1
        assert len(notified) == 1


class TestPipelineStats:
    def test_empty_stats(self, conn):
        stats = get_pipeline_stats(conn)
        assert stats["total_found"] == 0
        assert stats["stages"] == {}

    def test_stats_with_deals(self, conn):
        mark_found(conn, SAMPLE_HIT)
        mark_found(conn, SAMPLE_CONTRACT_HIT)
        update_stage(conn, "mydealz:galaxy s26:abc123", "notified")

        stats = get_pipeline_stats(conn)
        assert stats["total_found"] == 2
        assert stats["stages"]["found"]["count"] == 1
        assert stats["stages"]["notified"]["count"] == 1
        assert stats["conversion"]["found_to_notified_pct"] == 50.0

    def test_best_deals(self, conn):
        mark_found(conn, SAMPLE_HIT)
        mark_found(conn, SAMPLE_CONTRACT_HIT)
        stats = get_pipeline_stats(conn)
        assert len(stats["best_deals"]) == 2
        # Contract deal has higher profit
        assert stats["best_deals"][0]["net_profit"] == 112.30


class TestFormatting:
    def test_stats_format(self, conn):
        mark_found(conn, SAMPLE_HIT)
        stats = get_pipeline_stats(conn)
        text = format_pipeline_stats(stats)
        assert "Deal-Pipeline Stats" in text
        assert "Gefunden" in text

    def test_deal_detail_format(self, conn):
        mark_found(conn, SAMPLE_HIT)
        deal = get_deal(conn, "mydealz:galaxy s26:abc123")
        text = format_deal_detail(deal)
        assert "Galaxy S26" in text
        assert "599" in text
        assert "+150" in text
