from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.eval.metrics import (
    PerLabelMetrics,
    score_document,
    score_corpus,
    format_report,
)
from ko_pii.eval.synth import GoldDocument, GoldSpan


def _det(label, start, end, text):
    return DetectionResult(
        label=label, text=text, start=start, end=end,
        risk_level=RiskLevel.HIGH,
    )


def _gold(label, start, end, text):
    return GoldSpan(label=label, start=start, end=end, text=text)


def test_perfect_match():
    doc = GoldDocument(
        text="A 880101-1234568 B", spans=[_gold("RRN", 2, 16, "880101-1234568")]
    )
    preds = [_det("RRN", 2, 16, "880101-1234568")]
    m = score_document(doc, preds)
    assert m["RRN"].tp == 1
    assert m["RRN"].fp == 0
    assert m["RRN"].fn == 0
    assert m["RRN"].precision == 1.0
    assert m["RRN"].recall == 1.0
    assert m["RRN"].f1 == 1.0


def test_partial_overlap_counts_as_tp_under_partial_mode():
    doc = GoldDocument(
        text="abcdef", spans=[_gold("RRN", 0, 6, "abcdef")]
    )
    preds = [_det("RRN", 2, 5, "cde")]  # overlap
    m = score_document(doc, preds, mode="partial")
    assert m["RRN"].tp == 1


def test_strict_requires_exact_offsets():
    doc = GoldDocument(text="abcdef", spans=[_gold("RRN", 0, 6, "abcdef")])
    preds = [_det("RRN", 1, 6, "bcdef")]
    m = score_document(doc, preds, mode="strict")
    assert m["RRN"].tp == 0
    assert m["RRN"].fn == 1
    assert m["RRN"].fp == 1


def test_false_positive_and_negative():
    doc = GoldDocument(
        text="abcdefghij",
        spans=[_gold("RRN", 0, 3, "abc"), _gold("PHONE", 5, 9, "fghi")],
    )
    preds = [_det("RRN", 0, 3, "abc")]  # only matches first
    m = score_document(doc, preds)
    assert m["RRN"].tp == 1
    assert m["PHONE"].fn == 1


def test_score_corpus_aggregates():
    doc1 = GoldDocument("aaaa", [_gold("RRN", 0, 4, "aaaa")])
    doc2 = GoldDocument("bbbb", [_gold("RRN", 0, 4, "bbbb")])

    def predict(text):
        return [_det("RRN", 0, 4, text)]

    rpt = score_corpus([doc1, doc2], predict)
    assert rpt.document_count == 2
    assert rpt.per_label["RRN"].tp == 2
    assert rpt.micro().f1 == 1.0


def test_format_report_contains_headers():
    doc = GoldDocument("aaaa", [_gold("RRN", 0, 4, "aaaa")])

    def predict(text):
        return [_det("RRN", 0, 4, text)]

    rpt = score_corpus([doc], predict)
    out = format_report(rpt)
    assert "정확도" in out  # 한국어 Precision
    assert "재현율" in out  # 한국어 Recall
    assert "F1" in out
    assert "(전체)" in out  # 한국어 micro
