import pytest

from ko_pii.core.types import RiskLevel
from ko_pii.patterns.account import detect


def _detect_list(text):
    return list(detect(text))


class TestAccountPositive:
    def test_with_keyword(self):
        results = _detect_list("계좌: 110-123-456789")
        assert len(results) == 1
        r = results[0]
        assert r.label == "ACCOUNT"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["digits"] == "110123456789"

    def test_keyword_with_번호(self):
        results = _detect_list("계좌번호 1234567890123")
        assert len(results) == 1
        assert results[0].extra["digits"] == "1234567890123"

    def test_hyphenated_short(self):
        results = _detect_list("계좌 123-45-6789012")
        assert len(results) == 1


class TestAccountNegative:
    def test_no_keyword(self):
        # No 계좌 → not detected
        assert _detect_list("110-123-456789") == []

    def test_too_short(self):
        # 8 digits < 10 minimum
        assert _detect_list("계좌 12345678") == []

    def test_too_long(self):
        # 17 digits > 16 maximum
        assert _detect_list("계좌 12345678901234567") == []


@pytest.mark.parametrize("anchor", ["계좌번호", "신한"])
@pytest.mark.parametrize("value", ["110-123-456789", "110123456789"])
@pytest.mark.parametrize("tail", [" 100000", " 1234", "\n100000", "\r\n1234", "\t1234"])
def test_following_numeric_field_does_not_change_account(anchor, value, tail):
    text = anchor + " " + value + tail
    results = _detect_list(text)
    assert len(results) == 1
    result = results[0]
    assert result.text == value
    assert text[result.start:result.end] == value
    assert result.extra["digits"] == "110123456789"


@pytest.mark.parametrize("value", [
    "110-123-456789", "110 123 456789", "110 - 123 - 456789",
    "110 123-456789", "110-123 456789", "1234 5678 9012 3456",
])
@pytest.mark.parametrize("placement", ["keyword", "before", "after"])
def test_supported_groups_and_bank_positions(value, placement):
    text = {
        "keyword": "계좌번호: " + value,
        "before": "신한은행 " + value,
        "after": value + " 신한은행",
    }[placement]
    results = _detect_list(text)
    assert len(results) == 1
    assert results[0].text == value
    assert results[0].extra["digits"] == value.replace(" ", "").replace("-", "")
    assert text[results[0].start:results[0].end] == value


@pytest.mark.parametrize("value", [
    "11012345678912345", "110-123-456789-12345", "1-" * 16 + "1", "1 - " * 16 + "1",
])
@pytest.mark.parametrize("placement", ["keyword", "before", "after"])
def test_overlong_candidate_is_not_sliced_to_a_valid_prefix_or_suffix(value, placement):
    text = {
        "keyword": "계좌번호: " + value,
        "before": "신한은행 " + value,
        "after": value + " 신한은행",
    }[placement]
    assert _detect_list(text) == []


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\t", "  ", "\u2028", "\u2029"])
def test_unrelated_numeric_groups_are_not_joined(separator):
    assert _detect_list("계좌번호 110" + separator + "123" + separator + "456789") == []


def test_invalid_candidate_does_not_hide_the_next_account():
    text = "신한 11012345678912345; 계좌번호 110-123-456789"
    results = _detect_list(text)
    assert [r.text for r in results] == ["110-123-456789"]


@pytest.mark.parametrize("value", ["110 123-456789", "110-123 456789", "110 123 456789"])
def test_mixed_groups_stop_before_an_overlong_following_amount(value):
    results = _detect_list("계좌번호 " + value + " 100000")
    assert [r.text for r in results] == [value]
