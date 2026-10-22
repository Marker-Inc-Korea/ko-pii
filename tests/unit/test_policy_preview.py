import copy
import json

import pytest

from ko_pii.policy_preview import compare_policies, main


def test_change_reports_actual_retention_without_values():
    before = {"include": ["PHONE", "EMAIL"], "strategy": "tokenize", "strategies": {"PHONE": "partial"}}
    original = copy.deepcopy(before)
    after = {**before, "strategies": {"PHONE": "redact"}}
    text = "018-2345-6789 user@example.com"
    report = compare_policies(text, before=before, after=after)
    assert report["changed_by_label"] == {"PHONE": 1}
    assert report["changes"][0]["before"]["output_state"] == "partial_strategy"
    assert report["changes"][0]["after"]["output_state"] == "replaced"
    serialized = json.dumps(report)
    assert all(value not in serialized for value in ("018-2345-6789", "user@example.com", "<EMAIL_1>", "018-****-6789"))
    assert before == original
    assert not report["whole_text_safety_assessed"]


@pytest.mark.parametrize("strategy", ["tokenize", "hashed", "fpe", "partial", "redact", "asterisk"])
def test_identical_policies_ignore_random_tokens(strategy):
    policy = {"include": ["EMAIL", "PHONE"], "strategy": strategy}
    result = compare_policies("user@example.com 010-2345-6789", before=policy, after=policy)
    assert result["changed_span_count"] == 0
    assert result["before_policy_sha256"] == result["after_policy_sha256"]


def test_exclusions_and_audit_do_not_masquerade_as_accuracy():
    result = compare_policies("성명: 홍길동", before={"include": ["PERSON"]},
                              after={"include": ["PERSON"], "person_exclusions": ["홍길동"]})
    assert result["changes"][0]["after"]["output_state"] == "not_detected"
    assert "홍길동" not in json.dumps(result, ensure_ascii=False)
    audit = compare_policies("010-2345-6789", before={"mode": "AUDIT"}, after={"mode": "STRICT"})
    assert audit["changes"][0]["before"]["output_state"] == "retained_by_policy"
    assert audit["changes"][0]["before"]["applied_strategy"] is None
    assert audit["changes"][0]["after"]["applied_strategy"] == "tokenize"
    assert compare_policies("", before={}, after={})["input_empty"]


@pytest.mark.parametrize("config", [{"vault": "secret"}, {"secondary_detector": object()},
                                      {"mode": "bad"}, {"strategies": {"PERSON": "bad"}}])
def test_no_external_state_or_adapter_accepted(config):
    with pytest.raises(ValueError):
        compare_policies("test", before=config, after={})


def test_cli_no_input_mutations_and_no_overwrite(tmp_path, capsys):
    source, before, after, output = [tmp_path / s for s in ("text.txt", "a.json", "b.json", "report.json")]
    source.write_text("user@example.com")
    before.write_text('{"mode":"AUDIT"}')
    after.write_text('{"mode":"STRICT"}')
    originals = [p.read_bytes() for p in (source, before, after)]
    args = [str(source), "--before", str(before), "--after", str(after)]
    assert main(args + ["--output", str(output)]) == 0
    assert "user@example.com" not in output.read_text()
    assert main(args + ["--output", str(before)]) == 1
    assert [p.read_bytes() for p in (source, before, after)] == originals
    assert "user@example.com" not in capsys.readouterr().err


def test_cli_rejects_config_stdin_without_reading_it(monkeypatch):
    from ko_pii import cli

    def unexpected_read(*args):
        pytest.fail("invalid settings must be rejected before reading input")

    monkeypatch.setattr(cli, "_read_structured_input", unexpected_read)
    assert main(["-", "--before", "-", "--after", "other.json"]) == 1


def test_limit_and_undetected_values_are_not_a_safety_pass():
    with pytest.raises(ValueError, match="100000"):
        compare_policies("x" * 100_001, before={}, after={})
    report = compare_policies("undetected personal details", before={"include": ["RRN"]},
                              after={"include": ["RRN"]})
    assert report["observed_span_count"] == 0
    assert report["scope"] == "union_of_observed_spans_not_gold"
    assert report["whole_text_safety_assessed"] is False
