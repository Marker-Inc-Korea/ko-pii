from ko_pii import Anonymizer, ProcessingMode, RiskLevel


def test_anonymizer_attaches_combined_risk():
    anon = Anonymizer(mode=ProcessingMode.STRICT)
    result = anon.process(
        "신청인 홍길동(880101-1234568) 연락처 010-1234-5678 "
        "이메일 hong@gov.kr 주소 서울특별시 종로구 세종대로 209"
    )
    cr = result.combined_risk
    assert cr is not None
    # RRN 등장 → 즉시 CRITICAL
    assert cr.combined_risk == RiskLevel.CRITICAL
    assert "RRN" in cr.distinct_identifiers
    # 준식별자도 다수
    assert len(cr.distinct_quasi) >= 3


def test_summary_contains_combined_info():
    anon = Anonymizer(mode=ProcessingMode.STRICT)
    result = anon.process("홍길동 010-1234-5678 hong@example.com")
    s = result.summary
    assert "combined_risk" in s
    assert "distinct_quasi_identifiers" in s
    assert s["combined_risk"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "INFO"}


def test_no_pii_returns_info():
    anon = Anonymizer(mode=ProcessingMode.STRICT)
    result = anon.process("그냥 평문입니다.")
    cr = result.combined_risk
    assert cr is not None
    assert cr.combined_risk == RiskLevel.INFO
