import json

import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.eval.domain import LabeledDocument, evaluate, main
from ko_pii.eval.output import assess_output
from ko_pii.eval.synth import GoldDocument, GoldSpan


PHONE = "010-1234-5678"


def phone_document():
    return LabeledDocument("sample-1", GoldDocument(PHONE, [GoldSpan("PHONE", 0, len(PHONE), PHONE)]))


@pytest.mark.parametrize("strategy", ["redact", "asterisk", "tokenize", "hashed", "fpe"])
def test_output_measures_actual_substitutions_without_copying_source(strategy):
    report = evaluate([phone_document()], labels=["PHONE"], output_mode=ProcessingMode.STRICT, output_strategy=strategy)
    assert report["output_evaluation"]["counts"]["replaced"] == 1
    assert report["output_evaluation"]["not_fully_replaced"] == 0
    assert PHONE not in json.dumps(report)


def test_detection_success_is_not_output_success_in_audit_mode():
    report = evaluate([phone_document()], labels=["PHONE"], output_mode=ProcessingMode.AUDIT)
    assert report["micro"]["tp"] == 1
    assert report["output_evaluation"]["counts"]["retained_by_policy"] == 1


def test_partial_strategy_is_not_certified_as_removal():
    report = evaluate([phone_document()], labels=["PHONE"], output_mode=ProcessingMode.STRICT, output_strategy="partial")
    assert report["output_evaluation"]["counts"]["partial_strategy"] == 1
    assert report["output_evaluation"]["not_fully_replaced"] == 1


def test_undetected_gold_is_a_miss_not_replaced():
    text = "synthetic secret"
    document = LabeledDocument("sample-1", GoldDocument(text, [GoldSpan("PERSON", 0, len(text), text)]))
    report = evaluate([document], labels=["PERSON"], output_mode=ProcessingMode.STRICT)
    assert report["output_evaluation"]["counts"]["missed"] == 1


def test_incomplete_detection_cannot_claim_full_replacement(monkeypatch):
    detection = DetectionResult(label="PHONE", text=PHONE[4:], start=4, end=len(PHONE), risk_level=RiskLevel.HIGH)
    monkeypatch.setattr("ko_pii.anonymizer.detect_all", lambda *args, **kwargs: [detection])
    result = Anonymizer(strategy="redact").process(PHONE)
    rows = assess_output(phone_document().gold, result, "redact")
    assert rows[0]["state"] == "partially_replaced"
    assert rows[0]["covered_source_characters"] == len(PHONE) - 4


def test_emitted_replacement_is_checked_not_just_block_decision(monkeypatch):
    monkeypatch.setattr("ko_pii.anonymizer.label_to_hangul", lambda label: PHONE)
    result = Anonymizer(strategy="redact").process(PHONE)
    assert assess_output(phone_document().gold, result, "redact")[0]["state"] == "literal_retained"


def test_trace_offsets_follow_repeated_and_unicode_input():
    text = "연락처: " + PHONE + " / " + PHONE
    result = Anonymizer(strategy="tokenize", include=["PHONE"]).process(text)
    assert len(result.substitutions) == 2
    for span in result.substitutions:
        assert text[span.start:span.end] == PHONE
        assert result.text[span.output_start:span.output_end] == "<PHONE_1>"


def test_trace_uses_original_offsets_after_unicode_normalization():
    source = "０１０-１２３４-５６７８"
    gold = GoldDocument(source, [GoldSpan("PHONE", 0, len(source), source)])
    result = Anonymizer(strategy="redact", include=["PHONE"]).process(source)
    assert assess_output(gold, result, "redact")[0]["state"] == "replaced"
    span = result.substitutions[0]
    assert result.text[span.output_start:span.output_end] == "[전화번호]"


def test_review_decision_is_not_treated_as_substitution(monkeypatch):
    detection = DetectionResult("PHONE", PHONE, 0, len(PHONE), RiskLevel.HIGH, 0.6)
    monkeypatch.setattr("ko_pii.anonymizer.detect_all", lambda *args, **kwargs: [detection])
    result = Anonymizer(strategy="redact").process(PHONE)
    assert result.review_items()
    assert not result.substitutions
    assert assess_output(phone_document().gold, result, "redact")[0]["state"] == "retained_by_policy"


def test_cli_retention_gate_writes_report_before_failure(tmp_path):
    source = tmp_path / "gold.jsonl"
    source.write_text(json.dumps({"id": "sample-1", "text": PHONE, "spans": [{"label": "PHONE", "start": 0, "end": len(PHONE)}]}), encoding="utf-8")
    output = tmp_path / "report.json"
    assert main([str(source), "--output", str(output), "--labels", "PHONE", "--output-mode", "AUDIT", "--fail-on-retained"]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["output_evaluation"]["not_fully_replaced"] == 1


def test_no_gold_is_not_claimed_as_an_accuracy_pass():
    report = evaluate([LabeledDocument("negative", GoldDocument("normal", []))], output_mode=ProcessingMode.STRICT)
    assert sum(report["output_evaluation"]["counts"].values()) == 0
    assert report["micro"]["recall"] is None
