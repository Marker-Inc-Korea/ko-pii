from ko_pii.modes.tokenize import tokenize
from ko_pii.patterns.rrn import detect as detect_rrn
from ko_pii.patterns.phone import detect as detect_phone
from ko_pii.vault.reversible import ReversibleVault


def _all(text):
    return list(detect_rrn(text)) + list(detect_phone(text))


class TestTokenizeBasics:
    def test_single_rrn_replaced(self):
        text = "신청인 880101-1234568 입니다"
        replaced, v = tokenize(text, detect_rrn(text))
        assert "880101-1234568" not in replaced
        assert "<RRN_1>" in replaced
        assert v.reveal("<RRN_1>") == "880101-1234568"

    def test_same_value_uses_same_token(self):
        text = "A 880101-1234568, B 880101-1234568 동일인"
        replaced, v = tokenize(text, detect_rrn(text))
        assert replaced.count("<RRN_1>") == 2
        assert "<RRN_2>" not in replaced

    def test_different_categories_get_separate_counters(self):
        text = "신청인 880101-1234568 연락처 010-1234-5678"
        replaced, v = tokenize(text, _all(text))
        assert "<RRN_1>" in replaced
        assert "<PHONE_1>" in replaced
        assert v.reveal("<RRN_1>") == "880101-1234568"
        assert v.reveal("<PHONE_1>") == "010-1234-5678"

    def test_empty_detections_returns_original(self):
        text = "그냥 평문"
        replaced, v = tokenize(text, [])
        assert replaced == text
        assert len(v) == 0

    def test_vault_reuse_keeps_token_ids(self):
        v = ReversibleVault(salt="s")
        t1, _ = tokenize("A 880101-1234568", detect_rrn("A 880101-1234568"), vault=v)
        t2, _ = tokenize(
            "B 950101-2345676", detect_rrn("B 950101-2345676"), vault=v
        )
        assert "<RRN_1>" in t1
        assert "<RRN_2>" in t2


class TestTokenizeOrder:
    def test_preserves_non_pii_text(self):
        text = "주민번호 880101-1234568. 끝."
        replaced, _ = tokenize(text, detect_rrn(text))
        assert replaced.startswith("주민번호 ")
        assert replaced.endswith(". 끝.")

    def test_multiple_replacements_in_order(self):
        text = "1번 880101-1234568, 2번 950101-2345676"
        replaced, _ = tokenize(text, detect_rrn(text))
        assert replaced == "1번 <RRN_1>, 2번 <RRN_2>"
