"""A higher-priority finding must not expose the rest of a full-mask span."""
import json

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, detect_all
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.core._coverage import protection_remainders
from ko_pii.core.modes import policy_for
from ko_pii.core.overlap import resolve_overlaps
from ko_pii.integrations.custom import CallableDetector
from ko_pii.reporting import explain


def detection(source, label, begin, end, risk, confidence=1.0):
    return DetectionResult(label, source[begin:end], begin, end, risk, confidence=confidence)


@pytest.mark.parametrize("strategy", ["redact", "tokenize", "asterisk", "hashed"])
def test_nested_full_mask_preserves_the_inner_finding_and_protects_both_sides(monkeypatch, strategy):
    source = "ABCDEFGHIJ"
    parent = detection(source, "ADDRESS", 0, 10, RiskLevel.MEDIUM)
    child = detection(source, "PHONE", 3, 7, RiskLevel.HIGH)
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: [parent, child])
    vault = ReversibleVault(salt="coverage", secret_key="test", fingerprint_iterations=1)
    result = Anonymizer(strategy=strategy, vault=vault).process(source)
    assert [(d.start, d.end) for d in result.substitutions] == [(0, 3), (3, 7), (7, 10)]
    assert [r.detection.label for r in result.detections] == ["ADDRESS", "PHONE", "ADDRESS"]
    assert result.detections[1].detection is child
    assert result.summary["overlap_protection"] == {"fragments": 2}
    for record in (result.detections[0], result.detections[2]):
        d = record.detection
        assert d.text == source[d.start:d.end]
        assert d.subrule_id == "protection.overlap-remainder.v1"
        assert d.extra["overlap_parent"] == {"label": "ADDRESS", "source_span": [0, 10]}
    if strategy == "tokenize":
        restored = result.text
        for entry in vault.entries():
            restored = restored.replace(entry.token, vault.reveal(entry.token))
        assert restored == source


def test_crossing_discarded_candidates_do_not_discard_each_others_remainders(monkeypatch):
    source = "ABCDEFGHIJKLMNO"
    candidates = [detection(source, "ADDRESS", 0, 9, RiskLevel.MEDIUM),
                  detection(source, "ACCOUNT", 5, 15, RiskLevel.HIGH, 0.95),
                  detection(source, "PHONE", 7, 10, RiskLevel.HIGH)]
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: candidates)
    result = Anonymizer(strategy="redact").process(source)
    assert result.text == "[주소][계좌번호][전화번호][계좌번호]"
    assert [(s.start, s.end) for s in result.substitutions] == [(0, 5), (5, 7), (7, 10), (10, 15)]


@pytest.mark.parametrize("tail", [" (010-1234-5678)", " (101동 1202호, 010-1234-5678)"])
def test_real_address_with_an_embedded_phone_does_not_become_unmasked(tail):
    address = "서울특별시 강남구 테헤란로 152"
    result = Anonymizer(strategy="redact").process("주소: " + address + tail)
    assert address not in result.text and "101동" not in result.text and "1202호" not in result.text
    assert "010-1234-5678" not in result.text
    assert any(r.detection.label == "PHONE" for r in result.detections)


def test_confirmed_person_inside_an_address_cannot_expose_the_street_or_floor():
    source = "성명: 김다은\n주소: 서울특별시 강남구 테헤란로 152 김다은 12층"
    result = Anonymizer(strategy="redact").process(source)
    assert all(value not in result.text for value in ("김다은", "테헤란로", "152", "12층"))


@pytest.mark.parametrize("mode", ["union", "role_split"])
def test_remainders_come_from_the_eligible_merged_candidates(monkeypatch, mode):
    source = "ABCDEFGHIJ"
    child = detection(source, "PHONE", 3, 7, RiskLevel.HIGH)
    parent = detection(source, "ADDRESS", 0, 10, RiskLevel.MEDIUM)
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: [child])
    extra = CallableDetector(lambda text: [parent])
    result = Anonymizer(strategy="redact", secondary_detector=extra, merge_mode=mode,
                        role_split_labels=["ADDRESS"]).process(source)
    assert result.text == "[주소][전화번호][주소]"


@pytest.mark.parametrize("mode", ["intersection", "fallback_secondary", "role_split"])
def test_merge_rejected_candidates_are_not_revived(monkeypatch, mode):
    source = "ABCDEFGHIJ"
    parent = detection(source, "ADDRESS", 0, 10, RiskLevel.MEDIUM)
    child = detection(source, "PHONE", 3, 7, RiskLevel.HIGH)
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: [parent, child])
    extra = CallableDetector(lambda text: [])
    result = Anonymizer(strategy="redact", secondary_detector=extra, merge_mode=mode,
                        role_split_labels=["ADDRESS"]).process(source)
    if mode == "fallback_secondary":
        assert result.text == "[주소][전화번호][주소]"
    elif mode == "intersection":
        assert result.text == source
    else:
        assert result.text == "ABC[전화번호]HIJ"


def test_enrich_primary_does_not_revive_secondary_coverage_that_overlaps_primary(monkeypatch):
    source = "ABCDEFGHIJ"
    child = detection(source, "PHONE", 3, 7, RiskLevel.HIGH)
    parent = detection(source, "ADDRESS", 0, 10, RiskLevel.MEDIUM)
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: [child])
    result = Anonymizer(strategy="redact", secondary_detector=CallableDetector(lambda text: [parent]),
                        merge_mode="enrich_primary").process(source)
    assert result.text == "ABC[전화번호]HIJ"


@pytest.mark.parametrize("strategy", ["partial", "fpe"])
def test_partial_and_fpe_parents_are_not_treated_as_complete_replacements(monkeypatch, strategy):
    source = "ABCDEFGHIJ"
    parent = detection(source, "ADDRESS", 0, 10, RiskLevel.MEDIUM)
    child = detection(source, "PHONE", 3, 7, RiskLevel.HIGH)
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: [parent, child])
    result = Anonymizer(strategy="redact", strategies={"ADDRESS": strategy}).process(source)
    assert result.text == "ABC[전화번호]HIJ"
    assert "overlap_protection" not in result.summary


def test_a_selected_partial_strategy_is_not_overridden_by_its_parent(monkeypatch):
    source = "before 01012345678 after"
    candidates = [detection(source, "ADDRESS", 0, len(source), RiskLevel.MEDIUM),
                  detection(source, "PHONE", 7, 18, RiskLevel.HIGH)]
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: candidates)
    result = Anonymizer(strategy="redact", strategies={"PHONE": "partial"}).process(source)
    assert "before" not in result.text and "after" not in result.text
    assert "5678" in result.text
    assert result.detections[1].strategy == "partial"


def test_audit_filters_and_low_level_detection_keep_their_own_contracts():
    source = "주소: 서울특별시 강남구 테헤란로 152 (010-1234-5678)"
    audit = Anonymizer(mode=ProcessingMode.AUDIT)
    result = audit.process(source)
    assert result.text == source and not result.substitutions and not audit.vault.entries()
    filtered = Anonymizer(strategy="redact", include=["PHONE"]).process(source)
    assert "테헤란로 152" in filtered.text and "010-1234-5678" not in filtered.text
    assert [(d.label, d.text) for d in detect_all(source)] == [("PHONE", "010-1234-5678")]


def test_fragment_reporting_explains_derived_spans_without_exposing_values(monkeypatch):
    source = "ABCDEFGHIJ"
    candidates = [detection(source, "ADDRESS", 0, 10, RiskLevel.MEDIUM),
                  detection(source, "PHONE", 3, 7, RiskLevel.HIGH)]
    monkeypatch.setattr("ko_pii.anonymizer._detect_candidates", lambda *a, **k: candidates)
    result = Anonymizer(strategy="redact", trace_limit=10).process(source)
    report = explain(result, include_trace=True)
    assert report["overlap_trace"]["stages"]["protection"] == {"candidates": 3, "kept": 3, "discarded": 0}
    assert report["findings"][0]["subrule_id"] == "protection.overlap-remainder.v1"
    assert report["overlap_resolution"].startswith("block_risk_confidence_length_start;")
    assert all(value not in json.dumps(report) for value in (source, "ABC", "DEFG", "HIJ"))


def test_nested_parent_sweep_pushes_each_candidate_once(monkeypatch):
    import ko_pii.core._coverage as coverage

    source = "x" * 20_000
    parents = [detection(source, "ADDRESS", i, len(source) - i, RiskLevel.MEDIUM)
               for i in range(2_000)]
    child = detection(source, "PHONE", 9_000, 9_010, RiskLevel.HIGH)
    candidates = [*parents, child]
    policy = policy_for(ProcessingMode.STRICT)
    selected = resolve_overlaps(candidates, policy=policy)
    calls = []
    original_push = coverage.heapq.heappush

    def counted_push(heap, item):
        calls.append(item[-1])
        original_push(heap, item)

    monkeypatch.setattr(coverage.heapq, "heappush", counted_push)
    fragments = protection_remainders(source, candidates, selected, policy, lambda label: "redact")
    assert len(calls) == len(set(calls)) == len(parents)
    assert [(d.start, d.end) for d in fragments] == [(0, 9_000), (9_010, len(source))]
