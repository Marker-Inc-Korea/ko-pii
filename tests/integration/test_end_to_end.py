"""End-to-end integration: realistic Korean public-sector document → anonymized output."""
from __future__ import annotations

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.reporting.certificate import generate_certificate


_SAMPLE = """
[기획재정부 결재공문]

수신자: 행정안전부 장관
참조: 김민수 과장

본 안건과 관련하여 다음 사항을 보고드립니다.

신청인: 홍길동
주민등록번호: 880101-1234568
연락처: 010-1234-5678
이메일: hong@example.go.kr
주소: 서울특별시 종로구 세종대로 209

위 사항을 확인하여 주시기 바랍니다.

기안자: 박영수 사무관
""".strip()


def test_full_pipeline_tokenize():
    anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
    result = anon.process(_SAMPLE)
    # Sensitive originals must not survive
    for original in (
        "880101-1234568", "010-1234-5678",
        "hong@example.go.kr", "홍길동",
    ):
        assert original not in result.text

    labels = set(result.summary["by_label"].keys())
    assert {"RRN", "PHONE", "EMAIL", "PERSON"}.issubset(labels)

    # Vault must be able to reveal each tokenized value
    for entry in result.vault.entries():
        assert entry.original


def test_full_pipeline_redact():
    anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact")
    result = anon.process(_SAMPLE)
    assert "[주민등록번호]" in result.text
    assert "[전화번호]" in result.text
    assert "[이메일]" in result.text


def test_certificate_does_not_leak_originals():
    anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
    result = anon.process(_SAMPLE)
    cert = generate_certificate(result, document_id="public-doc-001")
    for original in (
        "880101-1234568", "010-1234-5678", "hong@example.go.kr",
    ):
        assert original not in cert


def test_audit_mode_passes_through():
    anon = Anonymizer(mode=ProcessingMode.AUDIT)
    result = anon.process(_SAMPLE)
    assert result.text == _SAMPLE
    # All BLOCKs become ALLOW under AUDIT
    actions = {r.action.value for r in result.detections}
    assert actions == {"ALLOW"}
