from ko_pii.core.types import RiskLevel
from ko_pii.patterns.frn import detect


def _detect_list(text):
    return list(detect(text))


class TestFRNPositive:
    def test_gender_5_male_1900s(self):
        results = _detect_list("외국인등록번호 850315-5345676")
        assert len(results) == 1
        r = results[0]
        assert r.label == "FRN"
        assert r.text == "850315-5345676"
        assert r.risk_level == RiskLevel.CRITICAL
        assert r.confidence == 1.0
        assert r.extra["gender_digit"] == 5
        assert r.extra["birth_date"] == "1985-03-15"
        assert r.extra["checksum_valid"] is True

    def test_gender_6_female_1900s(self):
        results = _detect_list("850315-6000008")
        assert len(results) == 1
        assert results[0].extra["gender_digit"] == 6
        assert results[0].extra["birth_date"] == "1985-03-15"

    def test_gender_7_male_2000s(self):
        results = _detect_list("외국인 000101-7000009")
        assert len(results) == 1
        assert results[0].extra["gender_digit"] == 7
        assert results[0].extra["birth_date"] == "2000-01-01"

    def test_gender_8_female_2000s(self):
        results = _detect_list("000101-8000001")
        assert len(results) == 1
        assert results[0].extra["gender_digit"] == 8
        assert results[0].extra["birth_date"] == "2000-01-01"

    def test_without_hyphen(self):
        results = _detect_list("8503155345676")
        assert len(results) == 1
        assert results[0].text == "8503155345676"

    def test_legal_basis_attached(self):
        results = _detect_list("850315-5345676")
        assert "출입국관리법" in results[0].legal_basis
        assert results[0].extra["category"] == "고유식별정보"

    def test_post_2020_frn_reduced_confidence(self):
        # gender 5, valid date, but wrong checksum
        results = _detect_list("850315-5345670")
        assert len(results) == 1
        assert results[0].confidence == 0.7
        assert results[0].extra["checksum_valid"] is False


class TestFRNNegative:
    def test_korean_national_gender_1_skipped(self):
        # gender 1 → Korean national, handled by patterns.rrn
        assert _detect_list("880101-1234568") == []

    def test_korean_national_gender_2_skipped(self):
        assert _detect_list("950101-2345676") == []

    def test_korean_national_gender_3_skipped(self):
        assert _detect_list("000101-3000008") == []

    def test_korean_national_gender_0_skipped(self):
        # 1800s Korean (rare but valid in RRN scheme)
        assert _detect_list("880101-0000000") == []

    def test_invalid_month(self):
        # gender 5 but month 13
        assert _detect_list("881305-5345676") == []

    def test_invalid_day(self):
        assert _detect_list("880231-5345676") == []

    def test_too_short(self):
        assert _detect_list("850315") == []

    def test_embedded_in_longer_digits(self):
        # 14 digits — surrounding-digit lookaround blocks
        assert _detect_list("88503155345676") == []
