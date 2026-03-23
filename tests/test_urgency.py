"""Tests for deal urgency detection."""

import pytest
from app.urgency import detect_urgency, urgency_weight, format_urgency


class TestDetectUrgency:
    """Core urgency detection tests."""

    def test_no_urgency(self):
        result = detect_urgency("iPhone 15 Pro 256GB für 899€")
        assert result["level"] == "none"
        assert result["score"] == 0
        assert result["signals"] == []

    def test_stock_low_numeric(self):
        result = detect_urgency("iPhone 15 nur noch 3 Stück verfügbar")
        assert result["level"] == "critical"
        assert "stock_low" in result["signals"]
        assert result["score"] >= 8

    def test_stock_low_higher_count(self):
        result = detect_urgency("iPhone 15 nur noch 15 verfügbar")
        assert "stock_low" in result["signals"]
        assert result["score"] == 8.0  # no +2 bonus for >3

    def test_stock_phrase_wenige(self):
        result = detect_urgency("Samsung TV - nur noch wenige verfügbar")
        assert result["level"] in ("medium", "high")
        assert "stock_phrase" in result["signals"]

    def test_stock_phrase_begrenzt(self):
        result = detect_urgency("Begrenzte Stückzahl bei MediaMarkt")
        assert "stock_phrase" in result["signals"]

    def test_time_limited_heute(self):
        result = detect_urgency("nur heute: MacBook Air für 799€")
        assert "time_limited" in result["signals"]
        assert result["score"] >= 4

    def test_time_limited_endet(self):
        result = detect_urgency("Aktion endet heute!")
        assert "time_limited" in result["signals"]

    def test_time_limited_bis(self):
        result = detect_urgency("Gültig bis 25.03.2026")
        assert "time_limited" in result["signals"]

    def test_flash_kurzzeitig(self):
        result = detect_urgency("Kurzzeitig: Pixel 8 für 399€")
        assert "flash" in result["signals"]
        assert result["score"] >= 6

    def test_flash_blitzangebot(self):
        result = detect_urgency("Blitzangebot bei Amazon - schnell zugreifen!")
        assert "flash" in result["signals"]

    def test_combined_signals(self):
        result = detect_urgency(
            "Nur noch 2 Stück - Blitzangebot endet heute!"
        )
        assert result["level"] == "critical"
        assert result["score"] == 10.0
        assert len(result["signals"]) >= 2

    def test_description_checked(self):
        result = detect_urgency(
            "Samsung Galaxy S24",
            description="Nur noch wenige verfügbar - zugreifen!"
        )
        assert result["level"] != "none"
        assert result["signals"]

    def test_empty_inputs(self):
        result = detect_urgency("", "")
        assert result["level"] == "none"

    def test_none_inputs(self):
        result = detect_urgency(None, None)
        assert result["level"] == "none"

    def test_case_insensitive(self):
        for text in [
            "NUR NOCH 5 STÜCK",
            "nur noch 5 stück",
            "Nur Noch 5 Stück",
        ]:
            result = detect_urgency(text)
            assert "stock_low" in result["signals"], f"Failed for: {text}"

    def test_solange_vorrat(self):
        result = detect_urgency("Solange der Vorrat reicht")
        assert "flash" in result["signals"]


class TestUrgencyWeight:
    """Weight multiplier tests."""

    def test_critical_weight(self):
        assert urgency_weight("critical") == 2.0

    def test_high_weight(self):
        assert urgency_weight("high") == 1.5

    def test_medium_weight(self):
        assert urgency_weight("medium") == 1.2

    def test_low_weight(self):
        assert urgency_weight("low") == 1.0

    def test_none_weight(self):
        assert urgency_weight("none") == 1.0

    def test_unknown_weight(self):
        assert urgency_weight("bogus") == 1.0


class TestFormatUrgency:
    """Formatting tests."""

    def test_critical_format(self):
        result = format_urgency({"level": "critical", "score": 10.0, "signals": [], "details": []})
        assert "🚨" in result
        assert "CRITICAL" in result

    def test_high_format(self):
        result = format_urgency({"level": "high", "score": 7.5, "signals": [], "details": []})
        assert "⚡" in result
        assert "HIGH" in result

    def test_medium_format(self):
        result = format_urgency({"level": "medium", "score": 4.0, "signals": [], "details": []})
        assert "⏰" in result

    def test_low_empty(self):
        result = format_urgency({"level": "low", "score": 1.0, "signals": [], "details": []})
        assert result == ""

    def test_none_empty(self):
        result = format_urgency({"level": "none", "score": 0, "signals": [], "details": []})
        assert result == ""


class TestRealWorldPatterns:
    """Realistic German deal text patterns."""

    def test_mydealz_stock_urgency(self):
        result = detect_urgency(
            "[Amazon] PS5 Slim - nur noch 7 Stück - 449€"
        )
        assert result["level"] != "none"

    def test_mydealz_flash(self):
        result = detect_urgency(
            "[MediaMarkt] Kurzzeitig: Bose QC Ultra für 229€"
        )
        assert "flash" in result["signals"]

    def test_preisjaeger_time(self):
        result = detect_urgency(
            "Lenovo ThinkPad Aktion endet heute - 599€"
        )
        assert "time_limited" in result["signals"]

    def test_normal_deal_no_false_positive(self):
        normal_deals = [
            "iPhone 15 Pro Max für 999€ bei Amazon",
            "Samsung Galaxy S24 Ultra - bester Preis",
            "Nintendo Switch OLED zum Bestpreis",
            "Dyson V15 Detect für 449€",
        ]
        for deal in normal_deals:
            result = detect_urgency(deal)
            assert result["level"] == "none", f"False positive for: {deal}"
