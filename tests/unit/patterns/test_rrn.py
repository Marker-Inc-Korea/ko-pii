from ko_pii.core.types import RiskLevel
from ko_pii.patterns.rrn import detect


def _detect_list(text):
    return list(detect(text))


class TestRRNPositive:
    def test_with_hyphen(self):
        results = _detect_list("주민번호: 880101-1234568")
        assert len(results) == 1
        r = results[0]
        assert r.label == "RRN"
        assert r.text == "880101-1234568"
        assert r.risk_level == RiskLevel.CRITICAL
        assert r.confidence == 1.0
        assert r.extra["checksum_valid"] is True
        assert r.extra["birth_date"] == "1988-01-01"

    def test_without_hyphen(self):
        results = _detect_list("주민번호 8801011234568 입니다")
        assert len(results) == 1
        assert results[0].text == "8801011234568"

    def test_legal_basis_attached(self):
        results = _detect_list("880101-1234568")
        assert results[0].legal_basis == "개인정보보호법 제24조의2"
        assert results[0].extra["category"] == "고유식별정보"

    def test_space_wrapped_hyphen(self):
        # 서식 표기 '880101 - 1234568' (공백+하이픈+공백, 3자) — 체크섬 프로브에서
        # 발견된 미검출 갭 회귀 테스트.
        results = _detect_list("주민번호 : 880101 - 1234568 조회 요청.")
        assert len(results) == 1
        assert results[0].text == "880101 - 1234568"
        assert results[0].extra["checksum_valid"] is True

    def test_hyphen_then_space(self):
        results = _detect_list("주민번호 880101- 1234568")
        assert len(results) == 1
        assert results[0].text == "880101- 1234568"

    def test_three_pure_spaces_not_matched(self):
        # 구분자 없는 공백 3자는 표 칼럼 나열일 가능성 — 매치 비허용 유지.
        assert _detect_list("880101   1234568") == []

    def test_foreigner_gender_digits_skipped(self):
        # gender_digit ∈ {5,6,7,8} = foreigner, handled by patterns.frn —
        # the RRN detector must not claim these.
        assert _detect_list("850315-5345676") == []  # foreigner male, 1900s
        assert _detect_list("850315-6000008") == []  # foreigner female, 1900s
        assert _detect_list("000101-7000009") == []  # foreigner male, 2000s
        assert _detect_list("000101-8000001") == []  # foreigner female, 2000s

    def test_multiple_rrns_in_one_text(self):
        text = "신청인 880101-1234568, 보호자 950101-2345676 동의함"
        results = _detect_list(text)
        assert len(results) == 2
        assert {r.text for r in results} == {"880101-1234568", "950101-2345676"}

    def test_2000s_gender_digit(self):
        # gender_digit 3 → 2000s male. 000101-3 → 2000-01-01.
        # Need a checksum-valid one to test.
        # weights × digits for "000101300000X":
        # digits: 0,0,0,1,0,1,3,0,0,0,0,0
        # products: 0,0,0,5,0,7,24,0,0,0,0,0  → sum = 36
        # 36 % 11 = 3, check = (11-3) % 10 = 8
        results = _detect_list("000101-3000008")
        assert len(results) == 1
        assert results[0].extra["birth_date"] == "2000-01-01"
        assert results[0].extra["checksum_valid"] is True

    def test_post_2020_rrn_reduced_confidence(self):
        # Valid pattern + valid date but checksum off → confidence 0.7
        results = _detect_list("880101-1234567")  # check digit should be 8
        assert len(results) == 1
        r = results[0]
        assert r.extra["checksum_valid"] is False
        assert r.confidence == 0.7
        # Still CRITICAL because post-2020 RRNs can fail checksum
        assert r.risk_level == RiskLevel.CRITICAL

    def test_leap_year_feb29_accepted(self):
        # 1988-02-29 is a valid date (1988 is a leap year)
        results = _detect_list("880229-1000005")
        assert len(results) == 1
        assert results[0].extra["birth_date"] == "1988-02-29"


class TestRRNNegative:
    def test_invalid_month(self):
        # month 13
        assert _detect_list("881301-1234568") == []

    def test_invalid_day(self):
        # Feb 31 is never valid
        assert _detect_list("880231-1234568") == []

    def test_non_leap_year_feb29(self):
        # 1989 is not a leap year
        assert _detect_list("890229-1234568") == []

    def test_too_short(self):
        assert _detect_list("880101") == []
        assert _detect_list("880101-12345") == []

    def test_embedded_in_longer_digit_run(self):
        # 14 digits with no separator — should not match
        assert _detect_list("12345678901234") == []

    def test_credit_card_like_not_matched(self):
        # 16-digit run with no separator
        assert _detect_list("1234567890123456") == []

    def test_leading_digits_block_match(self):
        # The lookbehind prevents matches when the would-be RRN is preceded
        # by another digit (no separator).
        assert _detect_list("99880101-1234568") == []

    def test_trailing_digits_block_match(self):
        # The lookahead prevents matches when followed by another digit.
        assert _detect_list("880101-12345689") == []


class TestRRNStructure:
    def test_span_indices_correct(self):
        text = "신청인의 주민등록번호는 880101-1234568 입니다."
        results = _detect_list(text)
        assert len(results) == 1
        r = results[0]
        assert text[r.start:r.end] == "880101-1234568"

    def test_evidence_strings_present(self):
        results = _detect_list("880101-1234568")
        ev = results[0].evidence
        assert any(e.startswith("pattern:rrn") for e in ev)
        assert any(e.startswith("date_valid:") for e in ev)
        assert "checksum:valid" in ev

    def test_evidence_for_failed_checksum(self):
        results = _detect_list("880101-1234567")
        ev = results[0].evidence
        assert "checksum:invalid_or_post_2020" in ev
        assert "checksum:valid" not in ev

    def test_front_and_back_groups_recorded(self):
        results = _detect_list("880101-1234568")
        assert results[0].extra["front"] == "880101"
        assert results[0].extra["back"] == "1234568"
