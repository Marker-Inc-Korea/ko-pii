from ko_pii.modes.redact import redact, label_to_hangul
from ko_pii.patterns.rrn import detect as detect_rrn
from ko_pii.patterns.phone import detect as detect_phone

import pytest


class TestRedactLabel:
    def test_replaces_with_hangul_label(self):
        text = "신청인 880101-1234568"
        out = redact(text, detect_rrn(text))
        assert out == "신청인 [주민등록번호]"

    def test_phone_label(self):
        text = "연락처 010-1234-5678"
        out = redact(text, detect_phone(text))
        assert out == "연락처 [전화번호]"


class TestRedactAsterisk:
    def test_length_preserving(self):
        text = "RRN 880101-1234568 끝"
        out = redact(text, detect_rrn(text), style="asterisk")
        assert "**************" in out
        assert "880101" not in out
        assert "1234568" not in out

    def test_custom_mask_char(self):
        text = "880101-1234568"
        out = redact(text, detect_rrn(text), style="asterisk", mask_char="#")
        assert out == "#" * len("880101-1234568")


class TestRedactFixed:
    def test_fixed_three_stars(self):
        text = "880101-1234568"
        out = redact(text, detect_rrn(text), style="fixed")
        assert out == "***"


class TestRedactErrors:
    def test_unknown_style_raises(self):
        with pytest.raises(ValueError):
            redact("text", [], style="unknown")


class TestLabelToHangul:
    def test_known_labels(self):
        assert label_to_hangul("RRN") == "주민등록번호"
        assert label_to_hangul("EMAIL") == "이메일"
        assert label_to_hangul("PERSON") == "성명"

    def test_unknown_label_passthrough(self):
        assert label_to_hangul("CUSTOM") == "CUSTOM"
