from itertools import permutations
import random

import pytest

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.eval.metrics import (
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


def test_partial_matching_is_invariant_to_gold_and_prediction_order():
    spans = [_gold("PERSON", 0, 2, "ab"), _gold("PERSON", 2, 4, "cd")]
    predictions = [_det("PERSON", 1, 3, "bc"), _det("PERSON", 0, 1, "a")]
    for gold_order in permutations(spans):
        for prediction_order in permutations(predictions):
            m = score_document(GoldDocument("abcd", list(gold_order)), iter(prediction_order))["PERSON"]
            assert (m.tp, m.fp, m.fn, m.f1) == (2, 0, 0, 1.0)


@pytest.mark.parametrize("mode", ["strcit", "PARTIAL", "", None, [], 1])
def test_invalid_matching_mode_rejected_even_for_empty_data(mode):
    with pytest.raises(ValueError, match="match mode"):
        score_document(GoldDocument(""), [], mode=mode)
    with pytest.raises(ValueError, match="match mode"):
        score_corpus([], lambda text: [], mode=mode)


def test_partial_one_prediction_cannot_confirm_two_gold_spans():
    doc = GoldDocument("abcd", [_gold("PERSON", 0, 2, "ab"), _gold("PERSON", 2, 4, "cd")])
    m = score_document(doc, [_det("PERSON", 0, 4, "abcd")])["PERSON"]
    assert (m.tp, m.fp, m.fn) == (1, 0, 1)


def test_strict_duplicate_spans_are_matched_once_each():
    doc = GoldDocument("ab", [_gold("PERSON", 0, 2, "ab")])
    m = score_document(doc, [_det("PERSON", 0, 2, "ab")] * 2, mode="strict")["PERSON"]
    assert (m.tp, m.fp, m.fn) == (1, 1, 0)


def test_matching_agrees_with_exhaustive_small_graph_oracle():
    from ko_pii.eval.metrics import _matching_size

    def oracle(edges, index=0, used=frozenset()):
        if index == len(edges):
            return 0
        choices = [oracle(edges, index + 1, used)]
        choices.extend(1 + oracle(edges, index + 1, used | {p})
                       for p in edges[index] if p not in used)
        return max(choices)

    rng = random.Random(20261027)
    for _ in range(200):
        predictions, gold = rng.randrange(7), rng.randrange(7)
        edges = [[p for p in range(predictions) if rng.choice([False, True])] for _ in range(gold)]
        assert _matching_size(edges, predictions) == oracle(edges)


def test_matching_long_augmenting_path_does_not_use_python_recursion():
    from ko_pii.eval.metrics import _matching_size

    edges = [[i, i + 1] for i in range(1500)] + [[0]]
    assert _matching_size(edges, 1501) == 1501
