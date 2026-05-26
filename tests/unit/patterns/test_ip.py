from ko_pii.core.types import RiskLevel
from ko_pii.patterns.ip import detect


def _detect_list(text):
    return list(detect(text))


class TestIPPositive:
    def test_standard_private(self):
        results = _detect_list("서버 192.168.0.1 에 접속")
        assert len(results) == 1
        r = results[0]
        assert r.label == "IP"
        assert r.text == "192.168.0.1"
        assert r.extra["version"] == 4
        assert r.risk_level == RiskLevel.MEDIUM

    def test_public_dns(self):
        results = _detect_list("DNS: 8.8.8.8")
        assert len(results) == 1

    def test_boundary_zero(self):
        results = _detect_list("게이트웨이 0.0.0.0")
        assert len(results) == 1

    def test_boundary_max(self):
        results = _detect_list("브로드캐스트 255.255.255.255")
        assert len(results) == 1

    def test_multiple_ips(self):
        text = "client 10.0.0.5 → server 10.0.0.10"
        results = _detect_list(text)
        assert len(results) == 2


class TestIPNegative:
    def test_octet_over_255(self):
        assert _detect_list("256.0.0.1") == []
        assert _detect_list("192.168.1.300") == []

    def test_octet_too_many_digits(self):
        assert _detect_list("1000.0.0.1") == []

    def test_three_octets_only(self):
        assert _detect_list("192.168.1") == []

    def test_letters_not_matched(self):
        assert _detect_list("192.168.x.1") == []

    def test_embedded_in_longer_dotted(self):
        # An extra dotted segment after a valid-looking IP
        assert _detect_list("1.2.3.4.5") == []
