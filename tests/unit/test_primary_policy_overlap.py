"""Do not discard usable primary evidence before applying output policy."""
import json

import pytest

from ko_pii import Anonymizer, ProcessingMode, detect_all
from ko_pii.cli import main
from ko_pii.core.modes import Action
from ko_pii.integrations.custom import RegexDetector
from ko_pii.profile import PolicyProfile
from ko_pii.reporting import explain
from ko_pii.streaming import PreForwardAnonymizer
from ko_pii.structured import anonymize_json


VALUE = "9001011234567"
TEXT = "\uacc4\uc88c\ubc88\ud638: " + VALUE


@pytest.mark.parametrize("value", [VALUE, "900101-1234567", "\uff19\uff10\uff10\uff11\uff10\uff11\uff11\uff12\uff13\uff14\uff15\uff16\uff17"])
@pytest.mark.parametrize("entry", ["text", "json", "profile", "stream"])
def test_account_is_masked_when_rrn_candidate_is_only_review(value, entry):
    source = "\uacc4\uc88c\ubc88\ud638: " + value
    anon = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact")
    if entry == "text":
        output = anon.process(source).text
    elif entry == "json":
        output = anonymize_json({"note": source}, anonymizer=anon).data["note"]
    elif entry == "profile":
        profile = PolicyProfile({"mode": "BALANCED", "strategy": "redact"})
        output = profile.process_json({"note": source}).data["note"]
    else:
        stream = PreForwardAnonymizer(anonymizer=anon)
        stream.feed(source[:8])
        stream.feed(source[8:])
        output = stream.finalize().text
    assert output == "\uacc4\uc88c\ubc88\ud638: [\uacc4\uc88c\ubc88\ud638]"


def test_adding_a_review_candidate_cannot_undo_an_existing_block():
    narrow = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact", include=["ACCOUNT"])
    broader = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact", include=["ACCOUNT", "RRN"])
    assert broader.process(TEXT).text == narrow.process(TEXT).text


@pytest.mark.parametrize("mode", ["union", "intersection", "cross_validation", "enrich_primary", "fallback_secondary"])
def test_secondary_matching_uses_primary_candidates_before_deduplication(mode):
    secondary = RegexDetector(VALUE, label="ACCOUNT", confidence=0.95)
    result = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact",
                       secondary_detector=secondary, merge_mode=mode).process(TEXT)
    assert VALUE not in result.text
    assert [(r.detection.label, r.action) for r in result.detections] == [("ACCOUNT", Action.BLOCK)]


def test_role_split_removes_delegated_label_before_it_can_hide_primary_account():
    secondary = RegexDetector("will-not-match", label="RRN")
    result = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact", secondary_detector=secondary,
                       merge_mode="role_split", role_split_labels=["RRN"]).process(TEXT)
    assert VALUE not in result.text
    assert result.detections[0].detection.label == "ACCOUNT"


@pytest.mark.parametrize("mode,action", [
    (ProcessingMode.STRICT, Action.BLOCK), (ProcessingMode.PARANOID, Action.BLOCK),
    (ProcessingMode.PERMISSIVE, Action.REVIEW), (ProcessingMode.AUDIT, Action.ALLOW),
])
def test_existing_nonconflicting_mode_priority_is_preserved(mode, action):
    result = Anonymizer(mode=mode, strategy="redact").process(TEXT)
    assert result.detections[0].detection.label == "RRN"
    assert result.detections[0].action == action
    assert (VALUE in result.text) == (action != Action.BLOCK)


def test_raw_detection_api_remains_policy_independent():
    found = detect_all(TEXT)
    assert [(d.label, d.confidence) for d in found] == [("RRN", 0.7)]


def test_filtered_candidates_cannot_be_reintroduced_by_policy_selection():
    result = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact", exclude=["ACCOUNT"]).process(TEXT)
    assert result.text == TEXT and result.review_items()


def test_primary_trace_describes_block_first_selection_without_source_values():
    result = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact", trace_limit=10).process(TEXT)
    report = explain(result, include_trace=True)
    assert report["overlap_resolution"].startswith("block_risk_confidence_length_start;")
    event = report["overlap_trace"]["discarded"][0]
    assert event["stage"] == "primary"
    assert event["reason"] == "non_blocking_policy_priority"
    assert event["candidate"]["label"] == "RRN"
    assert event["blocker"]["label"] == "ACCOUNT"
    assert VALUE not in json.dumps(report)


def test_cli_masks_account_and_reports_actual_selected_label(tmp_path):
    source, output, report = [tmp_path / name for name in ("in.txt", "out.txt", "report.json")]
    source.write_text(TEXT, encoding="utf-8")
    assert main([str(source), "--mode", "BALANCED", "--strategy", "redact", "-o", str(output),
                 "--explain", str(report), "--trace-limit", "10"]) == 0
    assert VALUE not in output.read_text(encoding="utf-8")
    assert json.loads(report.read_text(encoding="utf-8"))["findings"][0]["label"] == "ACCOUNT"
