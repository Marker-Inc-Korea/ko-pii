from ko_pii.core.types import RiskLevel
from ko_pii.patterns.pnu import detect


def _d(text):
    return list(detect(text))


class TestPnuPositive:
    def test_seoul_jongro(self):
        # 종로구 세종로 1번지 (가상 PNU): 시도 11(서울) + 시군구 110(종로) + 동
        # 116(세종로) + 리 00 + 일반필지 1 + 본번 0001 + 부번 0000
        results = _d("토지: 1111011600100010000 입니다")
        assert len(results) == 1
        r = results[0]
        assert r.label == "PNU"
        assert r.risk_level == RiskLevel.LOW
        assert r.extra["sido_code"] == "11"
        assert r.extra["bonbun"] == 1
        assert r.extra["bubun"] == 0
        assert r.extra["parcel_type"] == "1"

    def test_san_parcel(self):
        # 산번지 (필지구분 2)
        results = _d("PNU: 4129010200200500015")
        assert len(results) == 1
        assert results[0].extra["is_san"] is True

    def test_with_bubun(self):
        # 본번 + 부번 모두 있는 경우
        results = _d("4111016500100020003")
        assert len(results) == 1
        assert results[0].extra["bonbun"] == 2
        assert results[0].extra["bubun"] == 3


class TestPnuNegative:
    def test_invalid_sido(self):
        # 99 = 잘못된 시도 코드
        assert _d("9911011600100010000") == []

    def test_bonbun_all_zero(self):
        # 본번 0000 → 실제 토지 아님
        assert _d("1111011600100000000") == []

    def test_too_short(self):
        assert _d("111101160010001000") == []  # 18자리

    def test_too_long(self):
        assert _d("11110116001000100009") == []  # 20자리

    def test_embedded_in_longer_digits(self):
        assert _d("X1111011600100010000X") != []  # 비숫자 boundary OK
        # 앞뒤 숫자 boundary
        assert _d("11111011600100010000") == []  # 20자리 (boundary fail)

    def test_parcel_type_zero(self):
        # 필지구분 0 = invalid
        assert _d("1111011600000010000") == []


class TestPnuStructure:
    def test_legal_basis(self):
        r = _d("1111011600100010000")[0]
        assert "공간정보" in r.legal_basis
        assert r.extra["category"] == "참조정보"

    def test_evidence_includes_sido(self):
        r = _d("1111011600100010000")[0]
        assert any(e.startswith("sido:") for e in r.evidence)
