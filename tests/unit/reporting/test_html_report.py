from ko_pii import Anonymizer, ProcessingMode
from ko_pii.reporting.html_report import generate_html_report


def test_html_contains_essential_sections():
    anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
    text = "신청인 홍길동(880101-1234568) 연락처 010-1234-5678"
    result = anon.process(text)
    html_out = generate_html_report(text, result, document_id="doc-001")

    # 핵심 섹션
    assert "<!doctype html>" in html_out.lower()
    assert "doc-001" in html_out
    assert "원본" in html_out and "가명화" in html_out
    # 결합 위험도 배지
    assert "risk-CRITICAL" in html_out
    # 검출 카테고리 색상 표시
    assert "pii-RRN" in html_out
    assert "pii-PHONE" in html_out

    # 원본 텍스트는 PII 가 HTML span 으로 표시되어 있어야 — 원본은 그대로 표시 (마스킹 X)
    assert "880101-1234568" in html_out  # 원본 패널은 표시
    # 가명화 패널엔 토큰 들어 있어야
    assert "&lt;RRN_1&gt;" in html_out or "<RRN_1>" in html_out


def test_html_marking_buttons_for_review():
    anon = Anonymizer(mode=ProcessingMode.PERMISSIVE)  # 후-2020 RRN → REVIEW
    result = anon.process("주민번호 880101-1234567")
    html_out = generate_html_report("주민번호 880101-1234567", result)
    # REVIEW 항목엔 마킹 버튼 포함
    assert "mark(this" in html_out
    assert "exportMarks" in html_out


def test_html_no_marking_when_disabled():
    anon = Anonymizer(mode=ProcessingMode.STRICT)
    result = anon.process("주민번호 880101-1234568")
    html_out = generate_html_report("주민번호 880101-1234568", result,
                                     enable_marking=False)
    assert "mark(this" not in html_out
