from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from ko_pii import ProcessingMode
from ko_pii.eval.domain import LabeledDocument, compare_reports, evaluate, load_dataset, main, validate_provenance
from ko_pii.eval.external import load_k_pii_bench
from ko_pii.eval.synth import GoldDocument, GoldSpan


def documents():
    return [
        LabeledDocument("a", GoldDocument("a@example.com", [GoldSpan("EMAIL", 0, 13, "a@example.com")]), "form", "clean"),
        # Bare prose separators are intentionally outside the email detector's subset.
        LabeledDocument("b", GoldDocument("a at example dot com", [GoldSpan("EMAIL", 0, 20, "a at example dot com")]), "chat", "obfuscated"),
        LabeledDocument("c", GoldDocument("ordinary", []), "chat", "negative"),
        LabeledDocument("d", GoldDocument("b@example.com", [GoldSpan("EMAIL", 0, 13, "b@example.com")])),
    ]


def test_slices_count_micro_and_output_without_rerunning(monkeypatch):
    from ko_pii import Anonymizer
    original = Anonymizer.process
    calls = []
    def process(self, text, **kwargs):
        calls.append(text)
        return original(self, text, **kwargs)
    monkeypatch.setattr(Anonymizer, "process", process)
    report = evaluate(documents(), labels=["EMAIL"], output_mode=ProcessingMode.STRICT)
    assert len(calls) == 4
    assert report["micro"]["tp"] == 2
    assert report["micro"]["fn"] == 1
    for summaries in report["slices"].values():
        assert sum(row["document_count"] for row in summaries) == 4
        for count in ("tp", "fp", "fn"):
            assert sum(row["micro"][count] for row in summaries) == report["micro"][count]
        assert sum(row["output_evaluation"]["not_fully_replaced"] for row in summaries) == 1
    variants = {row["value"]: row for row in report["slices"]["variant"]}
    assert variants["negative"]["micro"]["recall"] is None
    assert variants["obfuscated"]["per_label"]["EMAIL"]["fn"] == 1
    assert "a@example.com" not in json.dumps(report)


def test_metadata_changes_comparison_scope_and_order_stability():
    docs = documents()
    original = evaluate(docs, labels=["EMAIL"])
    reversed_report = evaluate(list(reversed(docs)), labels=["EMAIL"])
    assert original["dataset_sha256"] == reversed_report["dataset_sha256"]
    assert original["slices"] == reversed_report["slices"]
    compare_reports(reversed_report, original)
    docs[0] = replace(docs[0], variant="other")
    with pytest.raises(ValueError, match="corpus"):
        compare_reports(evaluate(docs, labels=["EMAIL"]), original)
    bare = evaluate([replace(d, domain=None, variant=None) for d in docs], labels=["EMAIL"])
    assert "slices" not in bare


@pytest.mark.parametrize("metadata", [None, [], {"unknown": "x"}, {"domain": "private text"},
                                      {"variant": 1}, {"variant": "x" * 65}])
def test_invalid_metadata(tmp_path, metadata):
    path = tmp_path / "data.jsonl"
    path.write_text(json.dumps({"id": "a", "text": "", "spans": [], "metadata": metadata}), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_dataset(path)
    assert "private text" not in str(exc.value)


def test_category_cap():
    docs = [LabeledDocument(str(i), GoldDocument("", []), domain=str(i)) for i in range(129)]
    with pytest.raises(ValueError, match="128 categories"):
        evaluate(docs)


def test_python_api_rejects_duplicate_ids_before_slice_aggregation():
    docs = documents()
    with pytest.raises(ValueError, match="unique"):
        evaluate([docs[0], replace(docs[1], id=docs[0].id)])


def test_shipped_synthetic_example():
    path = Path(__file__).parents[3] / "docs" / "examples" / "evaluation-slices.jsonl"
    report = evaluate(load_dataset(path), labels=["PHONE"], output_mode=ProcessingMode.STRICT)
    assert report["document_count"] == 6
    assert report["micro"]["tp"] == 5
    assert report["micro"]["fn"] == report["micro"]["fp"] == 0
    assert report["output_evaluation"]["not_fully_replaced"] == 0


def test_external_adapter_preserves_explicit_categories(tmp_path):
    path = tmp_path / "bench.jsonl"
    path.write_text(json.dumps({"doc_id": "a", "text": "", "entities": [], "domain": "finance",
                                "variant": "clean"}), encoding="utf-8")
    docs, metadata = load_k_pii_bench(path)
    assert docs[0].domain == "finance"
    assert docs[0].variant == "clean"
    assert metadata["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_provenance_bytes_verified_not_revision():
    source = '{"id":"a","text":"","spans":[]}\n'
    config = {"schema_version": 1, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
              "revision": "abc123", "split": "test-shard-01"}
    assert validate_provenance(config, source)["upstream_revision_verified"] is False
    with pytest.raises(ValueError, match="digest"):
        validate_provenance(config, source + "\n")
    with pytest.raises(ValueError):
        validate_provenance({**config, "schema_version": True}, source)
    with pytest.raises(ValueError):
        validate_provenance({**config, "revision": "secret value"}, source)
    report = evaluate(documents(), labels=["EMAIL"])
    with pytest.raises(ValueError, match="provenance"):
        compare_reports({**report, "provenance": config}, report)


def test_cli_manifest_and_slice_round_trip(tmp_path, capsys):
    data = tmp_path / "data.jsonl"
    data.write_text(json.dumps({"id": "a", "text": "a@example.com", "spans": [
        {"label": "EMAIL", "start": 0, "end": 13}], "metadata": {"domain": "forms", "variant": "clean"}
    }) + "\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    config = {"schema_version": 1, "source_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
              "revision": "synthetic-v1", "split": "regression"}
    manifest.write_text(json.dumps(config), encoding="utf-8")
    output = tmp_path / "report.json"
    args = [str(data), "--provenance", str(manifest), "--labels", "EMAIL", "--output", str(output)]
    assert main(args) == 0
    report = json.loads(output.read_text())
    assert report["provenance"]["source_sha256"] == config["source_sha256"]
    assert report["slices"]["domain"][0]["micro"]["tp"] == 1
    snapshot = output.read_bytes()
    data.write_text(data.read_text() + "\n", encoding="utf-8")
    assert main(args) == 2
    assert output.read_bytes() == snapshot
    assert "digest" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main([str(data), "--provenance", str(manifest), "--output", str(manifest)])
