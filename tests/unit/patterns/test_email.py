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


class TestEmailObfuscated:
    """GAP 3 — [at]/[dot]/공백 주입 난독화 이메일."""

    def test_bracketed_at_dot(self):
        results = _detect_list("hong [at] gmail [dot] com")
        assert len(results) == 1
        assert results[0].extra["value"] == "hong@gmail.com"
        assert results[0].extra.get("obfuscated") is True

    def test_paren_at_dot(self):
        results = _detect_list("user (at) example (dot) org")
        assert len(results) == 1
        assert results[0].extra["value"] == "user@example.org"

    def test_spaced_at_and_dot(self):
        results = _detect_list("hong gildong @ naver . com")
        assert len(results) == 1
        assert results[0].extra["value"] == "honggildong@naver.com"

    def test_text_span_is_original(self):
        # span 은 원본 난독화 문자열 전체를 덮어야(마스킹 시 잔여 없음).
        results = _detect_list("문의 admin [at] korea (dot) kr 으로")
        assert results[0].text == "admin [at] korea (dot) kr"

    def test_bare_word_at_dot_not_fp(self):
        # 맨단어 at/dot 은 산문 FP 위험으로 보수적 제외.
        assert _detect_list("meet at noon and talk dot point") == []
        assert _detect_list("admin at gov dot kr") == []


class TestEmailNegative:
    def test_no_at(self):
        assert _detect_list("hongexample.com") == []

    def test_no_domain_dot(self):
        assert _detect_list("hong@example") == []

    def test_consecutive_dots_local(self):
        assert _detect_list("foo..bar@example.com") == []

    def test_consecutive_dots_domain(self):
        assert _detect_list("foo@example..com") == []
