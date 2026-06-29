from ko_pii.patterns.phone import detect


def _d(text):
    return list(detect(text))


class TestPhoneInternational:
    def test_plus_82_mobile(self):
        results = _d("+82-10-1234-5678")
        assert len(results) == 1
        r = results[0]
        assert r.extra["international"] is True
        assert r.extra["type"] == "mobile"

    def test_0082_mobile(self):
        results = _d("0082 10 1234 5678")
        assert len(results) == 1
        assert results[0].extra["international"] is True

    def test_intl_does_not_double_count_domestic(self):
        results = _d("연락처 +82-10-1234-5678 입니다")
        assert len(results) == 1


class TestPhoneDomestic:
    def test_still_matches_domestic(self):
        results = _d("010-1234-5678")
        assert len(results) == 1
        assert results[0].extra["international"] is False


def test_phone_spaced_hyphen_separator():
    """' - '(공백+하이픈+공백, 3글자) 구분자 표기 변형 — 민원 서식에서 발견된 갭 회귀."""
    from ko_pii.patterns.phone import detect
    for text in [
        "010 - 1234 - 5678",
        "연 락 처 : 010 - 1234 - 5678",
        "02 - 123 - 4567",
        "031 - 123 - 4567",
    ]:
        dets = detect(text)
        assert any(d.label == "PHONE" for d in dets), f"미검출: {text!r}"
    # 비-전화 오탐 방지
    for text in ["버전 1.5 - 2024 - 모델", "범위 100 - 200 - 300"]:
        dets = detect(text)
        assert not any(d.label == "PHONE" for d in dets), f"오탐: {text!r}"
