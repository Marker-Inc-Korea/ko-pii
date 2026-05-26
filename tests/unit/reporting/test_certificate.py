from ko_pii import Anonymizer, ProcessingMode
from ko_pii.reporting.certificate import generate_certificate


def test_certificate_contains_summary_and_blocked_items():
    anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
    result = anon.process("신청인 880101-1234568 연락처 010-1234-5678")
    cert = generate_certificate(result, document_id="doc-001")
    assert "doc-001" in cert
    assert "처리 증명서" in cert
    assert "차단/치환 처리 항목" in cert
    # Originals must not leak
    assert "880101-1234568" not in cert
    assert "010-1234-5678" not in cert
    # But tokens are listed
    assert "<RRN_1>" in cert or "<PHONE_1>" in cert


def test_certificate_includes_review_block_when_present():
    anon = Anonymizer(mode=ProcessingMode.PERMISSIVE)
    result = anon.process("주민번호 880101-1234567")  # post-2020 → REVIEW
    cert = generate_certificate(result, document_id="doc-002")
    assert "검토 대기 항목" in cert
