import copy
import json

import pytest

from ko_pii import ProcessingMode
from ko_pii.eval.domain import compare_reports, evaluate, main
from ko_pii.eval.external import load_k_pii_bench


def fixture_row():
    return {"doc_id": "private-id", "text": "user@example.com ACME", "entities": [
        {"type": "EMAIL_ADDRESS", "start": 0, "end": 16, "surface": "user@example.com"},
        {"type": "ORGANIZATION", "start": 17, "end": 21, "surface": "ACME"},
    ]}


def test_external_adapter_records_unmapped_and_safe_ids(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(fixture_row()), encoding="utf-8")
    docs, metadata = load_k_pii_bench(path)
    assert docs[0].id != "private-id"
    assert [s.label for s in docs[0].gold.spans] == ["EMAIL"]
    assert metadata["unmapped_span_count"] == 1
    assert metadata["unmapped_spans"] == {"ORGANIZATION": 1}
    output = tmp_path / "eval.json"
    assert main([str(path), "--dataset-format", "k-pii-bench", "--labels", "EMAIL",
                 "--output-mode", "STRICT", "--output", str(output)]) == 0
    report = json.loads(output.read_text("utf-8"))
    assert report["per_label"]["EMAIL"]["tp"] == 1
    assert "user@example.com" not in output.read_text("utf-8")
    assert report["dataset_adapter"]["unmapped_span_count"] == 1


@pytest.mark.parametrize("change", ["surface", "offset", "unknown", "duplicate", "bool"])
def test_adapter_rejects_bad_gold(tmp_path, change):
    row = fixture_row()
    if change == "surface":
        row["entities"][0]["surface"] = "private-value"
    elif change == "offset":
        row["entities"][0]["end"] = 100
    elif change == "unknown":
        row["entities"][0]["type"] = "private-value"
    elif change == "bool":
        row["entities"][0]["start"] = False
    else:
        row["entities"].append(row["entities"][0])
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_k_pii_bench(path)
    assert "private-value" not in str(exc.value)


def test_output_baseline_delta_and_policy_identity(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(fixture_row()), encoding="utf-8")
    docs, _ = load_k_pii_bench(path)
    base = evaluate(docs, labels=["EMAIL"], output_mode=ProcessingMode.STRICT)
    new = copy.deepcopy(base)
    new["output_evaluation"]["documents"][0]["spans"][0]["state"] = "literal_retained"
    difference = compare_reports(new, base)
    assert difference["output"]["new_not_fully_replaced"] == 1
    assert difference["counts"]["new_false_negatives"] == 0
    assert compare_reports(base, new)["output"]["resolved_not_fully_replaced"] == 1
    new["output_evaluation"]["mode"] = "AUDIT"
    with pytest.raises(ValueError, match="policies differ"):
        compare_reports(new, base)


def test_output_baseline_requires_complete_annotations(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(fixture_row()), encoding="utf-8")
    docs, _ = load_k_pii_bench(path)
    report = evaluate(docs, labels=["EMAIL"], output_mode=ProcessingMode.STRICT)
    missing = copy.deepcopy(report)
    missing["output_evaluation"]["documents"][0]["spans"] = []
    with pytest.raises(ValueError, match="annotations"):
        compare_reports(report, missing)


def test_external_wrong_label_scope_rejected(tmp_path, capsys):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(fixture_row()), encoding="utf-8")
    assert main([str(path), "--dataset-format", "k-pii-bench", "--labels", "BUSINESS_REG",
                 "--output", str(tmp_path / "out.json")]) == 2
    assert not (tmp_path / "out.json").exists()


def test_retention_flag_requires_baseline_output(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(fixture_row()), encoding="utf-8")
    baseline, output = tmp_path / "base.json", tmp_path / "out.json"
    assert main([str(path), "--dataset-format", "k-pii-bench", "--output", str(baseline)]) == 0
    assert main([str(path), "--dataset-format", "k-pii-bench", "--output", str(output),
                 "--baseline", str(baseline), "--output-mode", "STRICT", "--fail-on-new-retained"]) == 2
    assert not output.exists()


def test_retention_cli_fails_when_replacement_regresses(tmp_path, monkeypatch):
    from ko_pii import Anonymizer

    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(fixture_row()), encoding="utf-8")
    baseline, output = tmp_path / "base.json", tmp_path / "out.json"
    common = [str(path), "--dataset-format", "k-pii-bench", "--labels", "EMAIL", "--output-mode", "STRICT"]
    assert main([*common, "--output", str(baseline)]) == 0
    monkeypatch.setattr(Anonymizer, "_apply", lambda self, text, to_block, trace: text)
    assert main([*common, "--baseline", str(baseline), "--fail-on-new-retained", "--output", str(output)]) == 1
    report = json.loads(output.read_text("utf-8"))
    assert report["comparison"]["output"]["new_not_fully_replaced"] == 1
    assert report["comparison"]["counts"]["new_false_negatives"] == 0
