import json
import random

import pytest

from ko_pii import Anonymizer, ProcessingMode, detect_all
from ko_pii.eval.output import assess_output
from ko_pii.eval.synth import GoldDocument, GoldSpan
from ko_pii.reporting import explain, generate_certificate


def test_mixed_strategies_one_pass_and_output_assessment():
    text = "주민번호 880101-1234568 전화 010-2345-6789 메일 user@example.com"
    overrides = {"RRN": "redact", "PHONE": "partial"}
    anon = Anonymizer(strategy="tokenize", strategies=overrides, include=["RRN", "PHONE", "EMAIL"])
    overrides["RRN"] = "partial"
    result = anon.process(text)
    assert "[주민등록번호]" in result.text
    assert "010-****-6789" in result.text
    assert "<EMAIL_1>" in result.text
    assert result.vault.reveal("<EMAIL_1>") == "user@example.com"
    assert len(result.substitutions) == 3
    gold = GoldDocument(text, [GoldSpan(r.detection.label, r.detection.start, r.detection.end,
                                       r.detection.text) for r in result.detections])
    states = {r["label"]: r["state"] for r in assess_output(gold, result, "tokenize")}
    assert states == {"RRN": "replaced", "PHONE": "partial_strategy", "EMAIL": "replaced"}
    assert {r["applied_strategy"] for r in explain(result)["findings"]} == {"redact", "partial", "tokenize"}


@pytest.mark.parametrize("overrides", [{"NO_LABEL": "redact"}, {"PHONE": "typo"}, {"PHONE": []}, "redact"])
def test_invalid_policy_rejected(overrides):
    with pytest.raises(ValueError):
        Anonymizer(strategies=overrides)


def test_override_does_not_bypass_audit_mode():
    text = "메일 user@example.com"
    result = Anonymizer(mode=ProcessingMode.AUDIT, strategies={"EMAIL": "asterisk"}).process(text)
    assert result.text == text
    assert not result.substitutions
    assert explain(result)["findings"][0]["reason"] == "retained_by_policy"


def test_default_report_excludes_every_sensitive_channel():
    value = "880101-1234567"
    result = Anonymizer(mode=ProcessingMode.PERMISSIVE, include=["RRN"]).process(value)
    result.detections[0].detection.extra["raw"] = value
    result.detections[0].detection.evidence.append(f"date_valid:{value}")
    result.detections[0].detection.rule_id = value
    result.summary["combined_rationale"] = [value]
    assert value not in generate_certificate(result, document_id=value)
    assert value not in json.dumps(explain(result))
    assert value in generate_certificate(result, include_review_details=True)
    assert value in generate_certificate(result, document_id=value, include_document_id=True)
    assert "검토 대기 항목" in generate_certificate(result)


def test_partial_replacement_is_opt_in_in_certificate():
    result = Anonymizer(strategy="partial", include=["PHONE"]).process("010-2345-6789")
    assert "010-****-6789" not in generate_certificate(result)
    assert "010-****-6789" in generate_certificate(result, include_replacements=True)


@pytest.mark.parametrize("value", ["user@예시.kr", "user+tag@부서.예시.co.kr", "user@xn--vv4b11d.kr"])
def test_korean_idn_domain(value):
    text = f"😀 메일: {value}으로 보냈다."
    result = Anonymizer(strategy="redact", include=["EMAIL"]).process(text)
    assert result.text == "😀 메일: [이메일]으로 보냈다."
    assert result.detections[0].detection.text == value


@pytest.mark.parametrize("value", ["foo..bar@예시.kr", ".foo@예시.kr", "foo@-예시.kr"])
def test_invalid_idn(value):
    assert not detect_all(value, include=["EMAIL"])


@pytest.mark.parametrize("seed", range(16))
def test_normalization_and_substitution_invariants(seed):
    rng = random.Random(seed)
    value = "010-2345-6789"
    noisy = "".join(chr(ord(c) + 0xFEE0) if c.isdigit() and rng.choice([True, False]) else c for c in value)
    if seed % 2:
        noisy = noisy[:6] + "\u200b" + noisy[6:]
    prefix = "😀 연락처: " * (seed % 3)
    text = prefix + noisy + " 끝"
    result = Anonymizer(strategy="redact", include=["PHONE"]).process(text)
    assert result.text == prefix + "[전화번호] 끝"
    for rec in result.detections:
        d = rec.detection
        assert text[d.start:d.end] == d.text
    for span in result.substitutions:
        assert result.text[span.output_start:span.output_end] == "[전화번호]"
    report = explain(result)
    assert report["findings"][0]["rule_id"] == "ko-pii.phone.v1"
    assert noisy not in json.dumps(report, ensure_ascii=False)


def test_model_identifier_boundary_remains_conservative():
    # A default global ASCII boundary filter would hide adjacent real numbers.
    # This known policy-dependent false positive is not silently called fixed.
    assert detect_all("모델명 MODEL010-2345-6789CODE", include=["PHONE"])
    assert detect_all("TEL010-2345-6789", include=["PHONE"])
