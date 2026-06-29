from ko_pii.core.types import RiskLevel
from ko_pii.patterns.phone import detect


def _detect_list(text):
    return list(detect(text))


class TestPhoneMobile:
    def test_010_hyphen(self):
        results = _detect_list("연락처: 010-1234-5678")
        assert len(results) == 1
        r = results[0]
        assert r.label == "PHONE"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["type"] == "mobile"
        assert r.extra["digits_only"] == "01012345678"

    def test_010_no_separator(self):
        results = _detect_list("01012345678")
        assert len(results) == 1
        assert results[0].extra["type"] == "mobile"

    def test_010_with_spaces(self):
        results = _detect_list("010 1234 5678")
        assert len(results) == 1
        assert results[0].extra["digits_only"] == "01012345678"

    def test_010_with_dots(self):
        results = _detect_list("010.1234.5678")
        assert len(results) == 1

    def test_011_legacy_mobile(self):
        results = _detect_list("011-987-6543")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "011"


class TestPhoneLandline:
    def test_seoul_4_digit_middle(self):
        results = _detect_list("02-1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "landline"
        assert results[0].extra["prefix"] == "02"

    def test_seoul_3_digit_middle(self):
        results = _detect_list("02-123-4567")
        assert len(results) == 1
        assert results[0].extra["digits_only"] == "021234567"

    def test_gyeonggi_031(self):
        results = _detect_list("031-1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "landline"
        assert results[0].extra["prefix"] == "031"

    def test_busan_051(self):
        results = _detect_list("051-987-6543")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "051"


class TestPhoneVoIP:
    def test_070(self):
        results = _detect_list("070-1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "voip"
        assert results[0].extra["prefix"] == "070"


class TestPhoneParenArea:
    """GAP 4 — 괄호로 감싼 지역번호 표기 '(0NN) ...'."""

    def test_paren_mobile(self):
        results = _detect_list("(010) 9876-5432")
        assert len(results) == 1
        assert results[0].extra["type"] == "mobile"
        assert results[0].text == "(010) 9876-5432"

    def test_paren_seoul(self):
        results = _detect_list("(02) 1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "landline"
        assert results[0].text == "(02) 1234-5678"

    def test_paren_regional(self):
        results = _detect_list("(031) 123-4567")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "031"

    def test_paren_voip(self):
        results = _detect_list("(070) 1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "voip"

    def test_paren_no_space(self):
        results = _detect_list("연락처 (010)9876-5432 입니다")
        assert len(results) == 1
        assert results[0].text == "(010)9876-5432"

    def test_paren_non_phone_not_fp(self):
        # 유효 prefix 가 아니면 미검출 — '(2024) 발표' 등.
        assert _detect_list("(2024) 발표자료") == []
        assert _detect_list("(123) 항목 참조") == []


class TestPhoneNegative:
    def test_unknown_prefix(self):
        # 099 not a valid Korean phone prefix
        assert _detect_list("099-1234-5678") == []

    def test_too_short(self):
        assert _detect_list("010-123-456") == []

    def test_embedded_in_longer_digits(self):
        assert _detect_list("010123456789012") == []

    def test_only_prefix(self):
        assert _detect_list("010") == []


def test_phone_spaced_hyphen_separator():
    """' - '(공백+하이픈+공백) 구분자 표기 변형 검출."""
    from ko_pii.patterns.phone import detect
    for text in ["010 - 1234 - 5678", "연 락 처 : 010 - 1234 - 5678",
                 "02 - 123 - 4567", "031 - 123 - 4567"]:
        assert any(d.label == "PHONE" for d in detect(text)), f"미검출: {text!r}"
    for text in ["버전 1.5 - 2024 - 모델", "범위 100 - 200 - 300"]:
        assert not any(d.label == "PHONE" for d in detect(text)), f"오탐: {text!r}"
