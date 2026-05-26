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
