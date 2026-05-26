from ko_pii import Anonymizer, ProcessingMode
from ko_pii.reporting.summary import format_summary_text, review_queue, summarize


def _result(text="신청인 880101-1234568 연락처 010-1234-5678"):
    return Anonymizer(mode=ProcessingMode.STRICT).process(text)


def test_summarize_returns_dict_with_expected_keys():
    s = summarize(_result())
    for key in ("total", "by_action", "by_risk", "by_label", "by_legal_basis"):
        assert key in s


def test_format_summary_text_contains_section_headers():
    out = format_summary_text(_result())
    assert "처리 모드" in out
    assert "[조치별 분포]" in out
    assert "[위험도별 분포]" in out
    assert "[카테고리별 분포]" in out
    assert "[법적 근거별 분포]" in out


def test_review_queue_extracts_review_actions_only():
    # PERMISSIVE → post-2020 RRN is REVIEW
    result = Anonymizer(mode=ProcessingMode.PERMISSIVE).process(
        "주민번호 880101-1234567"
    )
    q = review_queue(result.detections)
    assert len(q) >= 1
    assert all("label" in item for item in q)
