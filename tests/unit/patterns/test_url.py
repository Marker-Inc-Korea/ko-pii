from ko_pii.core.types import RiskLevel
from ko_pii.patterns.url import detect


def _detect_list(text):
    return list(detect(text))


class TestURLPositive:
    def test_http(self):
        results = _detect_list("자세히는 http://example.com 참조")
        assert len(results) == 1
        r = results[0]
        assert r.label == "URL"
        assert r.text == "http://example.com"
        assert r.risk_level == RiskLevel.INFO
        assert r.extra["scheme"] == "http"

    def test_https_with_path(self):
        results = _detect_list("https://www.korea.kr/news/123")
        assert len(results) == 1
        assert results[0].extra["scheme"] == "https"

    def test_with_query(self):
        results = _detect_list("https://example.com/search?q=ko-pii&page=1")
        assert len(results) == 1

    def test_with_port(self):
        results = _detect_list("https://localhost:8080/api")
        assert len(results) == 1

    def test_trailing_punctuation_trimmed(self):
        results = _detect_list("see https://example.com.")
        assert len(results) == 1
        assert results[0].text == "https://example.com"


class TestURLNegative:
    def test_no_scheme(self):
        assert _detect_list("example.com") == []

    def test_ftp_not_matched(self):
        # We only match http(s)
        assert _detect_list("ftp://files.example.com") == []
