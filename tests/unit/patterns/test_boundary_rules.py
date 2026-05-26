"""Boundary rule 회귀 — 과탐 방지용 명시 테스트."""
from ko_pii.patterns.passport import detect as detect_passport
from ko_pii.patterns.postal_code import detect as detect_postal
from ko_pii.patterns.vehicle import detect as detect_vehicle


# ─────────────────────────────────────────────────────────────────────
# VEHICLE — 한글 용도 코드 화이트리스트
# ─────────────────────────────────────────────────────────────────────

class TestVehicleHangulWhitelist:
    def test_private_use_codes_accepted(self):
        # 자가용 32자 일부
        for ch in ("가", "나", "다", "마", "어", "주"):
            assert len(list(detect_vehicle(f"12{ch}3456"))) == 1

    def test_commercial_codes(self):
        for ch in ("바", "사", "아", "자"):
            assert len(list(detect_vehicle(f"87{ch}1234"))) == 1

    def test_rental_codes(self):
        for ch in ("하", "허", "호"):
            assert len(list(detect_vehicle(f"99{ch}1234"))) == 1

    def test_diplomatic_and_military(self):
        for ch in ("외", "영", "준", "국", "합", "육", "해", "공"):
            assert len(list(detect_vehicle(f"01{ch}0001"))) == 1

    def test_random_hangul_rejected(self):
        # 일반 한글 — 차량 용도가 아닌 것들 → FP 거부
        for ch in ("강", "박", "광", "민", "한", "성", "현", "원"):
            assert list(detect_vehicle(f"12{ch}3456")) == []

    def test_zero_suffix_rejected(self):
        # 뒷 4자리 0000 = placeholder
        assert list(detect_vehicle("12가0000")) == []

    def test_purpose_classification(self):
        r = list(detect_vehicle("12가3456"))[0]
        assert r.extra["purpose"] == "private"
        r = list(detect_vehicle("87바1234"))[0]
        assert r.extra["purpose"] == "commercial"
        r = list(detect_vehicle("99하1234"))[0]
        assert r.extra["purpose"] == "rental"


# ─────────────────────────────────────────────────────────────────────
# POSTAL_CODE — 시·도 코드 화이트리스트
# ─────────────────────────────────────────────────────────────────────

class TestPostalCodeBoundary:
    def test_valid_prefixes_accepted(self):
        # 각 시·도 대표 prefix
        for prefix in ("03", "12", "22", "30", "41", "55", "63"):
            assert len(list(detect_postal(f"우편번호 {prefix}123"))) == 1

    def test_invalid_prefixes_rejected(self):
        # 09 (서울/경기 사이 갭), 20 (인천/강원 사이), 60 (전남/광주 사이), 99 (미할당)
        for prefix in ("09", "20", "60", "70", "80", "99", "00"):
            assert list(detect_postal(f"우편번호 {prefix}123")) == []

    def test_legacy_6digit_valid_prefix(self):
        # 첫 자리 1~7 만 허용 (구 우편번호 체계)
        assert len(list(detect_postal("123-456"))) == 1
        assert len(list(detect_postal("789-012"))) == 1  # 첫 자리 7 OK
        assert len(list(detect_postal("987-654"))) == 0  # 첫 자리 9 reject
        assert len(list(detect_postal("089-123"))) == 0  # 첫 자리 0 reject


# ─────────────────────────────────────────────────────────────────────
# PASSPORT — prefix 화이트리스트 + 신형 (PP/PR/PT 등)
# ─────────────────────────────────────────────────────────────────────

class TestPassportPrefixes:
    def test_single_letter_prefixes(self):
        for prefix in ("M", "S", "G", "O", "D", "R", "T"):
            results = list(detect_passport(f"{prefix}12345678"))
            assert len(results) == 1
            assert results[0].extra["prefix"] == prefix

    def test_two_letter_prefixes(self):
        for prefix in ("PP", "PM", "PS", "PO", "PD", "PR", "PT"):
            results = list(detect_passport(f"{prefix}12345678"))
            assert len(results) == 1

    def test_invalid_prefix_letters_rejected(self):
        for prefix in ("A", "B", "Z", "X", "AB", "ZZ"):
            assert list(detect_passport(f"{prefix}12345678")) == []

    def test_all_zero_serial_rejected(self):
        # placeholder
        assert list(detect_passport("M00000000")) == []
        assert list(detect_passport("PP00000000")) == []

    def test_passport_kind_classification(self):
        r = list(detect_passport("D12345678"))[0]
        assert r.extra["kind"] == "diplomatic"
        r = list(detect_passport("PO87654321"))[0]
        assert r.extra["kind"] == "official"
        r = list(detect_passport("PT11112222"))[0]
        assert r.extra["kind"] == "travel_cert"
