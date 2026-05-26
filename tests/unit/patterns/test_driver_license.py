from ko_pii.core.types import RiskLevel
from ko_pii.patterns.driver_license import detect


def _detect_list(text):
    return list(detect(text))


class TestDriverLicensePositive:
    def test_seoul_full_hyphen(self):
        results = _detect_list("운전면허번호 11-90-123456-78")
        assert len(results) == 1
        r = results[0]
        assert r.label == "DRIVER_LICENSE"
        assert r.text == "11-90-123456-78"
        assert r.risk_level == RiskLevel.CRITICAL
        assert r.confidence == 0.85
        assert r.extra["region_code"] == "11"
        assert r.extra["year_2digit"] == "90"
        assert r.extra["sequence"] == "123456"
        assert r.extra["check_2digit"] == "78"

    def test_incheon(self):
        results = _detect_list("23-15-654321-09")
        assert len(results) == 1
        assert results[0].extra["region_code"] == "23"

    def test_sejong(self):
        results = _detect_list("28-22-100000-50")
        assert len(results) == 1
        assert results[0].extra["region_code"] == "28"

    def test_no_hyphens_requires_keyword(self):
        # 하이픈 없는 12자리는 키워드 anchor 필수 (처방번호 등과 충돌 방지)
        assert _detect_list("119012345678") == []
        results = _detect_list("운전면허 119012345678")
        assert len(results) == 1
        assert results[0].extra["region_code"] == "11"
        assert results[0].extra["format"] == "compact"

    def test_partial_hyphens_not_supported(self):
        # 부분 하이픈은 더 이상 지원 안 함 — 전체 하이픈 또는 키워드 anchor 필요
        assert _detect_list("11-9012345678") == []
        results = _detect_list("면허번호 11-90-123456-78")
        assert len(results) == 1

    def test_legal_basis_attached(self):
        results = _detect_list("11-90-123456-78")
        assert "시행령 제19조" in results[0].legal_basis


class TestDriverLicenseNegative:
    def test_region_code_too_low(self):
        assert _detect_list("10-90-123456-78") == []
        assert _detect_list("09-90-123456-78") == []

    def test_region_code_too_high(self):
        assert _detect_list("29-90-123456-78") == []
        assert _detect_list("99-90-123456-78") == []

    def test_too_short(self):
        assert _detect_list("11-90-12345") == []
        assert _detect_list("11901234567") == []  # 11 digits

    def test_too_long(self):
        # 13 digits — lookarounds + length restriction block
        assert _detect_list("1190123456789") == []

    def test_embedded_in_longer_digit_run(self):
        assert _detect_list("119012345678901234") == []


class TestDriverLicenseStructure:
    def test_span_indices_correct(self):
        text = "면허증 11-90-123456-78 분실"
        results = _detect_list(text)
        assert len(results) == 1
        r = results[0]
        assert text[r.start:r.end] == "11-90-123456-78"
