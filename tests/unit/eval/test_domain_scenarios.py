"""Handwritten regression scenarios, not a held-out accuracy benchmark.

Parts construct offsets by concatenation, so repeated values stay distinct.
Known errors remain explicit assertions, not skipped or xfailed examples.
"""
from datetime import date

import pytest

from ko_pii.core.modes import ProcessingMode
from ko_pii.eval.domain import LabeledDocument, evaluate
from ko_pii.eval.synth import GoldDocument, GoldSpan


# A part is (text, gold label, expected prediction label).
SCENARIOS = [
    ("form-legacy-mobile", "forms", ["PHONE"], [
        ("연락처: ", None, None), ("018-234-6789", "PHONE", "PHONE")]),
    ("form-parenthesized", "forms", ["PHONE"], [
        ("전화: ", None, None), ("(018) 2345-6789", "PHONE", "PHONE")]),
    ("form-international", "forms", ["PHONE"], [
        ("Mobile: ", None, None), ("+82-18-2345-6789", "PHONE", "PHONE")]),
    ("form-rrn", "forms", ["RRN"], [
        ("주민등록번호: ", None, None), ("880101-1234568", "RRN", "RRN")]),
    ("form-name", "forms", ["PERSON"], [
        ("성명: ", None, None), ("김도구", "PERSON", "PERSON")]),
    ("form-address", "forms", ["ADDRESS"], [
        ("주소: ", None, None), ("서울특별시 강남구 테헤란로 152", "ADDRESS", "ADDRESS")]),
    ("chat-repeated-email", "chat", ["EMAIL"], [
        ("여기로 보내줘: ", None, None), ("user@example.com", "EMAIL", "EMAIL"),
        (". 다시 적을게 ", None, None), ("user@example.com", "EMAIL", "EMAIL")]),
    ("chat-idn-email", "chat", ["EMAIL"], [
        ("메일은 ", None, None), ("user@예시.kr", "EMAIL", "EMAIL"), (" 이야", None, None)]),
    ("chat-wide-digits", "chat", ["PHONE"], [
        ("전화해 ", None, None), ("０１０-２３４５-６７８９", "PHONE", "PHONE")]),
    ("chat-invisible-character", "chat", ["PHONE"], [
        ("연락줘 ", None, None), ("010-23\u200b45-6789", "PHONE", "PHONE")]),
    ("chat-obfuscated-email", "chat", ["EMAIL"], [
        ("메일 ", None, None), ("user[at]example.com", "EMAIL", "EMAIL")]),
    ("free-model-code-known-fp", "free_text", ["PHONE"], [
        ("MODEL", None, None), ("010-2345-6789", None, "PHONE"), ("CODE", None, None)]),
    ("free-attached-phone", "free_text", ["PHONE"], [
        ("TEL", None, None), ("010-2345-6789", "PHONE", "PHONE")]),
    ("free-unrelated-date", "free_text", ["DT_BIRTH"], [
        ("시행일자: 2026-05-21", None, None)]),
    ("free-common-word", "free_text", ["PERSON"], [
        ("이상 없음. 구현 결과를 확인했습니다.", None, None)]),
    ("free-product-numbers", "free_text", ["PHONE", "RRN"], [
        ("version 1.2.3, build 20261022, range 100-200-300", None, None)]),
    ("form-future-rrn-known-fn", "forms", ["RRN"], [
        ("Synthetic RRN: ", None, None), ("991231-3123456", "RRN", None)]),
]


def scenario_document(case_id, parts):
    text, gold, predictions = "", [], []
    for value, gold_label, prediction_label in parts:
        start = len(text)
        text += value
        if gold_label:
            gold.append(GoldSpan(gold_label, start, len(text), value))
        if prediction_label:
            predictions.append({"label": prediction_label, "start": start, "end": len(text)})
    return LabeledDocument(case_id, GoldDocument(text, gold)), predictions


@pytest.mark.parametrize("case_id,domain,labels,parts", SCENARIOS, ids=[c[0] for c in SCENARIOS])
def test_domain_scenarios(case_id, domain, labels, parts, monkeypatch):
    from ko_pii.patterns import rrn

    class EvaluationDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 22)

    # Isolate the deliberately future-dated synthetic RRN from the test clock.
    monkeypatch.setattr(rrn, "date", EvaluationDate)
    document, expected = scenario_document(case_id, parts)
    report = evaluate([document], labels=labels, output_mode=ProcessingMode.STRICT)
    row = report["documents"][0]
    assert sorted(row["predictions"], key=str) == sorted(expected, key=str), domain
    expected_spans = {(r["label"], r["start"], r["end"]) for r in expected}
    gold_spans = {(s.label, s.start, s.end) for s in document.gold.spans}
    assert len(row["false_negatives"]) == len(gold_spans - expected_spans)
    assert len(row["false_positives"]) == len(expected_spans - gold_spans)
    for span in report["output_evaluation"]["documents"][0]["spans"]:
        key = (span["label"], span["start"], span["end"])
        assert span["state"] == ("replaced" if key in expected_spans else "missed")
    assert report["evaluation_date"] == date.today().isoformat()


def test_scenarios_include_negatives_repetition_and_known_errors():
    assert {c[1] for c in SCENARIOS} == {"forms", "chat", "free_text"}
    assert any(not any(p[1] for p in c[3]) for c in SCENARIOS)
    assert any(p[1] and not p[2] for c in SCENARIOS for p in c[3])
    assert any(p[2] and not p[1] for c in SCENARIOS for p in c[3])
    case = next(c for c in SCENARIOS if c[0] == "chat-repeated-email")
    doc, _ = scenario_document(case[0], case[3])
    assert len(doc.gold.spans) == 2
    assert doc.gold.spans[0].text == doc.gold.spans[1].text
    assert doc.gold.spans[0].start != doc.gold.spans[1].start
