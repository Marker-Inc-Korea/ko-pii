import copy
import json

import pytest

from ko_pii.eval.domain import compare_reports, evaluate, load_dataset, main


def dataset(tmp_path, rows=None):
    path = tmp_path / "corpus.jsonl"
    if rows is None:
        rows = [
            {"id": "phone-1", "text": "010-1234-5678",
             "spans": [{"label": "PHONE", "start": 0, "end": 13}]},
            {"id": "name-1", "text": "성명: 김도구",
             "spans": [{"label": "PERSON", "start": 4, "end": 7}]},
        ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_measures_per_label_and_omits_original_values(tmp_path):
    documents = load_dataset(dataset(tmp_path))
    report = evaluate(documents, labels=["PHONE", "PERSON"])
    assert report["per_label"]["PHONE"]["tp"] == 1
    assert report["per_label"]["PERSON"]["tp"] == 1
    assert report["micro"]["recall"] == 1.0
    serialized = json.dumps(report, ensure_ascii=False)
    assert "김도구" not in serialized
    assert "010-1234-5678" not in serialized


def test_new_miss_is_detected_even_when_another_miss_is_resolved(tmp_path):
    docs = load_dataset(dataset(tmp_path))
    baseline = evaluate(docs, labels=["PHONE", "PERSON"])
    # Previous run found the name, but missed the phone.
    phone = next(row for row in baseline["documents"] if row["id"] == "phone-1")
    phone["predictions"] = []
    current = evaluate(docs, labels=["PHONE", "PERSON"], person_exclusions=["김도구"])
    comparison = compare_reports(current, baseline)
    assert comparison["counts"]["new_false_negatives"] == 1
    assert comparison["counts"]["resolved_false_negatives"] == 1
    assert comparison["new_false_negatives"] == [{"id": "name-1", "label": "PERSON", "start": 4, "end": 7}]


def test_comparison_recomputes_from_predictions_not_stale_summary(tmp_path):
    report = evaluate(load_dataset(dataset(tmp_path)), labels=["PHONE", "PERSON"])
    old = copy.deepcopy(report)
    old["micro"]["fn"] = 100
    old["documents"][0]["false_negatives"] = [{"bogus": True}]
    assert all(count == 0 for count in compare_reports(report, old)["counts"].values())


@pytest.mark.parametrize("field,value", [
    ("dataset_sha256", "other"), ("match_mode", "partial"),
    ("evaluated_labels", ["PHONE"]), ("schema_version", 99),
])
def test_rejects_incomparable_baseline(tmp_path, field, value):
    report = evaluate(load_dataset(dataset(tmp_path)))
    baseline = copy.deepcopy(report)
    baseline[field] = value
    with pytest.raises(ValueError, match=field):
        compare_reports(report, baseline)


def test_rejects_invalid_baseline_predictions(tmp_path):
    report = evaluate(load_dataset(dataset(tmp_path)))
    baseline = copy.deepcopy(report)
    baseline["documents"][0]["predictions"] = [{"label": "PERSON", "start": 1, "end": 9999}]
    with pytest.raises(ValueError, match="offsets"):
        compare_reports(report, baseline)


@pytest.mark.parametrize("bad_span", [
    {"label": "PHONE", "start": -1, "end": 13},
    {"label": "PHONE", "start": 0, "end": 14},
    {"label": "PHONE", "start": False, "end": 13},
    {"label": "INVALID", "start": 0, "end": 13},
])
def test_rejects_invalid_annotations(tmp_path, bad_span):
    path = dataset(tmp_path, [{"id": "sample", "text": "010-1234-5678", "spans": [bad_span]}])
    with pytest.raises(ValueError, match="dataset line 1"):
        load_dataset(path)


def test_empty_and_duplicate_documents_are_not_a_valid_evaluation(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        load_dataset(dataset(tmp_path, []))
    doc = {"id": "same", "text": "no identifiers", "spans": []}
    with pytest.raises(ValueError, match="unique"):
        load_dataset(dataset(tmp_path, [doc, doc]))


def test_no_positive_examples_have_no_measurable_recall(tmp_path):
    path = dataset(tmp_path, [{"id": "negative", "text": "plain text", "spans": []}])
    report = evaluate(load_dataset(path), labels=["PHONE"])
    assert report["micro"]["recall"] is None
    assert report["micro"]["f1"] is None


def test_document_order_does_not_change_corpus_identity(tmp_path):
    docs = load_dataset(dataset(tmp_path))
    before = evaluate(docs)
    after = evaluate(list(reversed(docs)))
    assert before["dataset_sha256"] == after["dataset_sha256"]
    assert all(value == 0 for value in compare_reports(after, before)["counts"].values())


def test_cli_comparison_exits_nonzero_and_keeps_report(tmp_path, capsys):
    path = dataset(tmp_path)
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "current.json"
    exclusions = tmp_path / "exclusions.txt"
    exclusions.write_text("김도구\n", encoding="utf-8")
    assert main([str(path), "--labels", "PHONE,PERSON", "--output", str(baseline)]) == 0
    rc = main([
        str(path), "--labels", "PHONE,PERSON", "--output", str(output),
        "--baseline", str(baseline), "--person-exclusions-file", str(exclusions),
        "--fail-on-new-misses",
    ])
    assert rc == 1
    report = json.loads(output.read_text())
    assert report["comparison"]["counts"]["new_false_negatives"] == 1
    assert "new_false_negatives: 1" in capsys.readouterr().out


def test_cli_reports_false_positive_changes(tmp_path):
    path = dataset(tmp_path, [{"id": "benign", "text": "성명: 김도구", "spans": []}])
    exclusions = tmp_path / "exclusions.txt"
    exclusions.write_text("김도구", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    assert main([str(path), "--output", str(baseline), "--labels", "PERSON",
                 "--person-exclusions-file", str(exclusions)]) == 0
    assert main([str(path), "--output", str(tmp_path / "after.json"), "--labels", "PERSON",
                 "--baseline", str(baseline), "--fail-on-new-false-positives"]) == 1


def test_cli_does_not_overwrite_source_or_baseline(tmp_path):
    path = dataset(tmp_path)
    before = path.read_bytes()
    with pytest.raises(SystemExit):
        main([str(path), "--output", str(path)])
    assert path.read_bytes() == before


def test_regression_gate_requires_baseline(tmp_path):
    with pytest.raises(SystemExit):
        main([str(dataset(tmp_path)), "--output", str(tmp_path / "out.json"), "--fail-on-new-misses"])
