"""Evaluation inputs must not silently change the measured annotation set."""
import copy
import json
from dataclasses import replace

import pytest

from ko_pii import ProcessingMode
from ko_pii.eval.domain import LabeledDocument, compare_reports, evaluate, main
from ko_pii.eval.output import OUTPUT_STATES
from ko_pii.eval.synth import GoldDocument, GoldSpan


PHONE = "010-1234-5678"
SPAN = GoldSpan("PHONE", 0, len(PHONE), PHONE)


def document(spans=None):
    return LabeledDocument("sample", GoldDocument(PHONE, [SPAN] if spans is None else spans))


@pytest.mark.parametrize("span", [
    replace(SPAN, label="PHNOE"), replace(SPAN, label=[]),
    replace(SPAN, start=False), replace(SPAN, start=0.0),
    replace(SPAN, start=-1), replace(SPAN, start=13),
    replace(SPAN, end=True), replace(SPAN, end=14),
    replace(SPAN, text="different synthetic source"), replace(SPAN, text=None),
])
def test_python_evaluation_rejects_invalid_gold_even_outside_label_scope(span):
    for labels in (["PHONE"], ["EMAIL"]):
        with pytest.raises(ValueError):
            evaluate([document([span])], labels=labels, output_mode=ProcessingMode.STRICT)


def test_duplicate_gold_is_not_scored_twice_or_hidden_by_set_rows():
    with pytest.raises(ValueError, match="duplicate span"):
        evaluate([document([SPAN, replace(SPAN)])])


@pytest.mark.parametrize("gold", [
    None, GoldDocument(None, []), GoldDocument(PHONE, None),
    GoldDocument(PHONE, [{}]), GoldDocument("bad\ud800text", []),
])
def test_python_evaluation_rejects_malformed_documents_without_source_in_error(gold):
    with pytest.raises(ValueError) as exc:
        evaluate([LabeledDocument("sample", gold)])
    assert PHONE not in str(exc.value)
    assert "bad\ud800text" not in str(exc.value)


def test_python_limits_match_file_document_and_span_limits(monkeypatch):
    monkeypatch.setattr("ko_pii.eval.domain.MAX_DOCUMENT_CHARS", 12)
    with pytest.raises(ValueError, match="character limit"):
        evaluate([document()])
    monkeypatch.setattr("ko_pii.eval.domain.MAX_DOCUMENT_CHARS", 100)
    monkeypatch.setattr("ko_pii.eval.domain.MAX_SPANS", 1)
    with pytest.raises(ValueError, match="bounded list"):
        evaluate([document([SPAN, replace(SPAN, label="PERSON")])])


def test_all_python_annotations_are_validated_before_any_detection(monkeypatch):
    calls = []

    def detect(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr("ko_pii.eval.domain.detect_all", detect)
    bad = replace(document([replace(SPAN, label="TYPO")]), id="z-last")
    with pytest.raises(ValueError):
        evaluate([document(), bad])
    assert calls == []


@pytest.mark.parametrize("mode", ["STRICT", "", False, 1])
def test_invalid_python_mode_is_rejected_before_processing(monkeypatch, mode):
    def process(*args, **kwargs):
        pytest.fail("invalid mode reached the anonymizer")

    monkeypatch.setattr("ko_pii.anonymizer.Anonymizer.process", process)
    with pytest.raises(ValueError, match="output_mode"):
        evaluate([document()], output_mode=mode)


def report():
    return evaluate([document(), LabeledDocument("negative", GoldDocument("ordinary", []))],
                    labels=["PHONE"], output_mode=ProcessingMode.STRICT)


@pytest.mark.parametrize("state,covered", [
    ("replaced", 0), ("replaced", 12), ("replaced", 14),
    ("replaced", -1), ("replaced", True), ("replaced", 13.0),
    ("replaced", "13"), ("replaced", None),
    ("partial_strategy", 0), ("literal_retained", 12),
    ("partially_replaced", 0), ("partially_replaced", 13),
    ("missed", 1), ("retained_by_policy", 13),
])
def test_output_comparison_rejects_impossible_coverage_on_both_sides(state, covered):
    original, invalid = report(), report()
    span = next(d for d in invalid["output_evaluation"]["documents"] if d["id"] == "sample")["spans"][0]
    span.update(state=state, covered_source_characters=covered)
    for pair in ((original, invalid), (invalid, original)):
        with pytest.raises(ValueError, match="covered characters"):
            compare_reports(*pair)


@pytest.mark.parametrize("state", OUTPUT_STATES)
def test_output_comparison_accepts_consistent_states_and_recomputes_changes(state):
    original, changed = report(), report()
    covered = (0 if state in ("missed", "retained_by_policy")
               else 4 if state == "partially_replaced" else len(PHONE))
    span = next(d for d in changed["output_evaluation"]["documents"] if d["id"] == "sample")["spans"][0]
    span.update(state=state, covered_source_characters=covered)
    result = compare_reports(changed, original)["output"]
    assert result["new_not_fully_replaced"] == int(state != "replaced")
    assert compare_reports(original, changed)["output"]["resolved_not_fully_replaced"] == int(state != "replaced")


@pytest.mark.parametrize("change", ["omit-negative", "extra-negative", "duplicate", "wrong-source-end"])
def test_output_document_set_and_source_coordinates_are_complete(change):
    original, invalid = report(), report()
    rows = invalid["output_evaluation"]["documents"]
    if change == "omit-negative":
        rows[:] = [r for r in rows if r["id"] != "negative"]
    elif change == "extra-negative":
        rows.append({"id": "not-in-corpus", "spans": []})
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    else:
        next(d for d in rows if d["id"] == "sample")["spans"][0]["end"] = 14
    for pair in ((original, invalid), (invalid, original)):
        with pytest.raises(ValueError):
            compare_reports(*pair)


@pytest.mark.parametrize("key,value", [
    ("contract", "unknown"), ("mode", "STRCIT"), ("strategy", "unknown"),
    ("strategies", {"PHNOE": "redact"}),
])
def test_equal_but_invalid_output_contracts_are_not_comparable(key, value):
    first, second = report(), report()
    first["output_evaluation"][key] = value
    second["output_evaluation"][key] = value
    with pytest.raises(ValueError):
        compare_reports(first, second)


@pytest.mark.parametrize("kind", ["duplicate-key", "nan", "infinity", "overflow", "deep"])
def test_cli_rejects_ambiguous_baseline_json_without_overwriting_report(tmp_path, capsys, kind):
    source, baseline, output = [tmp_path / name for name in ("input.jsonl", "baseline.json", "current.json")]
    source.write_text(json.dumps({"id": "sample", "text": PHONE,
                                 "spans": [{"label": "PHONE", "start": 0, "end": len(PHONE)}]}), encoding="utf-8")
    arguments = [str(source), "--labels", "PHONE", "--output-mode", "STRICT"]
    assert main([*arguments, "--output", str(baseline)]) == 0
    text = baseline.read_text(encoding="utf-8")
    extra = {"duplicate-key": '"package_version":"ambiguous",', "nan": '"extra":NaN,',
             "infinity": '"extra":Infinity,', "overflow": '"extra":1e999,',
             "deep": '"extra":' + '[' * 70 + '0' + ']' * 70 + ','}[kind]
    baseline.write_text(text.replace('{', '{' + extra, 1), encoding="utf-8")
    output.write_text("previous report", encoding="utf-8")
    assert main([*arguments, "--baseline", str(baseline), "--output", str(output),
                 "--fail-on-new-retained"]) == 2
    assert output.read_text(encoding="utf-8") == "previous report"
    error = capsys.readouterr().err
    assert "Traceback" not in error and PHONE not in error


def test_cli_rejects_inconsistent_retention_baseline_instead_of_reporting_no_regression(tmp_path):
    source, baseline, output = [tmp_path / name for name in ("input.jsonl", "baseline.json", "current.json")]
    source.write_text(json.dumps({"id": "sample", "text": PHONE,
                                 "spans": [{"label": "PHONE", "start": 0, "end": len(PHONE)}]}), encoding="utf-8")
    arguments = [str(source), "--labels", "PHONE", "--output-mode", "STRICT"]
    assert main([*arguments, "--output", str(baseline)]) == 0
    previous = json.loads(baseline.read_text(encoding="utf-8"))
    previous["output_evaluation"]["documents"][0]["spans"][0]["covered_source_characters"] = 0
    baseline.write_text(json.dumps(previous), encoding="utf-8")
    assert main([*arguments, "--baseline", str(baseline), "--output", str(output),
                 "--fail-on-new-retained"]) == 2
    assert not output.exists()
