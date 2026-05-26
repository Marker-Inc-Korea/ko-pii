from ko_pii.core.types import RiskLevel
from ko_pii.patterns.email import detect


def _detect_list(text):
    return list(detect(text))


class TestEmailPositive:
    def test_basic(self):
        results = _detect_list("문의: hong@example.com")
        assert len(results) == 1
        r = results[0]
        assert r.label == "EMAIL"
        assert r.text == "hong@example.com"
        assert r.risk_level == RiskLevel.MEDIUM
        assert r.extra["local"] == "hong"
        assert r.extra["domain"] == "example.com"

    def test_with_dot_in_local(self):
        results = _detect_list("kim.cs@gov.kr")
        assert len(results) == 1
        assert results[0].extra["local"] == "kim.cs"

    def test_with_plus_tag(self):
        results = _detect_list("user+tag@example.org")
        assert len(results) == 1
        assert "+" in results[0].extra["local"]

    def test_korean_gov_kr_domain(self):
        results = _detect_list("청장 minister@korea.kr 보고")
        assert len(results) == 1
        assert results[0].extra["domain"] == "korea.kr"

    def test_subdomain(self):
        results = _detect_list("info@mail.example.co.kr")
        assert len(results) == 1

    def test_multiple_emails(self):
        text = "참조: a@x.com, b@y.com, c@z.com"
        results = _detect_list(text)
        assert len(results) == 3


class TestEmailNegative:
    def test_no_at(self):
        assert _detect_list("hongexample.com") == []

    def test_no_domain_dot(self):
        assert _detect_list("hong@example") == []

    def test_consecutive_dots_local(self):
        assert _detect_list("foo..bar@example.com") == []

    def test_consecutive_dots_domain(self):
        assert _detect_list("foo@example..com") == []
