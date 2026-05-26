from ko_pii import Anonymizer, ProcessingMode, Action


class TestAnonymizerTokenize:
    def test_blocks_rrn_under_strict(self):
        anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
        result = anon.process("신청인 880101-1234568 입니다")
        assert "880101-1234568" not in result.text
        assert "<RRN_1>" in result.text
        # The vault holds the original
        assert result.vault is not None
        assert result.vault.reveal("<RRN_1>") == "880101-1234568"

    def test_review_items_carry_no_substitution(self):
        # Post-2020 RRN has confidence 0.7 → REVIEW under PERMISSIVE
        anon = Anonymizer(mode=ProcessingMode.PERMISSIVE)
        result = anon.process("주민번호 880101-1234567 입니다")
        review = result.review_items()
        assert any(r.detection.label == "RRN" for r in review)
        # Text unchanged because nothing was BLOCKed
        assert "880101-1234567" in result.text

    def test_audit_mode_does_not_modify_text(self):
        text = "신청인 880101-1234568"
        anon = Anonymizer(mode=ProcessingMode.AUDIT)
        result = anon.process(text)
        assert result.text == text
        # All detections were ALLOW
        assert all(r.action == Action.ALLOW for r in result.detections)


class TestAnonymizerRedact:
    def test_redact_produces_hangul_labels(self):
        anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact")
        result = anon.process("신청인 880101-1234568 연락처 010-1234-5678")
        assert "[주민등록번호]" in result.text
        assert "[전화번호]" in result.text

    def test_asterisk_preserves_length(self):
        anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="asterisk")
        result = anon.process("주민번호 880101-1234568")
        assert "*" * len("880101-1234568") in result.text


class TestAnonymizerHashed:
    def test_hashed_strategy(self):
        anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="hashed")
        result = anon.process("a 880101-1234568 b 880101-1234568")
        # Same value → same hash token
        import re
        toks = re.findall(r"<RRN:[0-9a-f]+>", result.text)
        assert len(toks) == 2
        assert toks[0] == toks[1]


class TestAnonymizerSummary:
    def test_summary_counts_total_and_actions(self):
        anon = Anonymizer(mode=ProcessingMode.STRICT)
        result = anon.process(
            "신청인 880101-1234568 / 보호자 950101-2345676 / 010-1234-5678"
        )
        s = result.summary
        assert s["total"] >= 3
        assert s["by_action"].get("BLOCK", 0) >= 2
        assert "RRN" in s["by_label"]
        assert "PHONE" in s["by_label"]

    def test_include_filter_narrows_detection(self):
        anon = Anonymizer(
            mode=ProcessingMode.STRICT, strategy="redact", include=["RRN"]
        )
        result = anon.process("주민번호 880101-1234568 연락처 010-1234-5678")
        assert "[주민등록번호]" in result.text
        # Phone NOT detected because of include filter
        assert "010-1234-5678" in result.text


class TestAnonymizerErrors:
    def test_unknown_strategy_raises(self):
        import pytest
        with pytest.raises(ValueError):
            Anonymizer(strategy="unknown")
