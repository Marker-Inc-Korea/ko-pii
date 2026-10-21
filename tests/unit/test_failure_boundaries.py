import hashlib
import json
import zipfile

import pytest

from ko_pii.batch import process_paths
from ko_pii import Anonymizer
from ko_pii.cli import main
from ko_pii.io_.bounded import BoundedReadError
from ko_pii.io_.isolated import read_text_isolated
from ko_pii.tabular import anonymize_value
from ko_pii.vault.reversible import ReversibleVault


def test_explicit_empty_vault_is_preserved():
    vault = ReversibleVault(salt="review-salt")
    token, actual = anonymize_value("synthetic-person", "PERSON", vault=vault)
    assert actual is vault, f"supplied vault has {len(vault)} entries; returned vault has {len(actual)}"
    assert vault.reveal(token) == "synthetic-person"


def test_explicit_empty_vault_keeps_fail_closed_audit():
    class FailingAudit:
        def record_store(self, *args, **kwargs):
            raise OSError("synthetic audit failure")

    vault = ReversibleVault(audit_log=FailingAudit(), audit_failure_policy="raise")
    with pytest.raises(OSError, match="synthetic audit failure"):
        anonymize_value("synthetic-person", "PERSON", vault=vault)


def test_cli_rejects_unknown_include(tmp_path, capsys):
    source = tmp_path / "input.txt"
    source.write_text("010-1234-5678", encoding="utf-8")
    try:
        code = main([str(source), "--include", "PHNOE", "--json-summary"])
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    assert code != 0, f"code={code}, stdout={captured.out!r}, stderr={captured.err!r}"


@pytest.mark.parametrize("extension", ["docx", "hwpx", "xlsx"])
def test_partial_parse_failure_rejects_document(tmp_path, extension):
    path = tmp_path / f"partial.{extension}"
    contents = {
        "docx": {
            "word/document.xml": '<document><p><t>ordinary body</t></p></document>',
            "word/header1.xml": '<header><p><t>010-1234-5678',
        },
        "hwpx": {
            "Contents/section0.xml": '<section><p><t>ordinary body</t></p></section>',
            "Contents/section1.xml": '<section><p><t>010-1234-5678',
        },
        "xlsx": {
            "xl/workbook.xml": '<workbook/>',
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>ordinary body</t></is></c></row></sheetData></worksheet>',
            "xl/worksheets/sheet2.xml": '<worksheet><row><c>010-1234-5678',
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in contents[extension].items():
            archive.writestr(name, content)
    with pytest.raises(BoundedReadError):
        document = read_text_isolated(path)
        print(f"accepted {extension}: {document.text!r}")


def test_batch_reports_missing_explicit_input(tmp_path):
    source = tmp_path / "present.txt"
    source.write_text("ordinary body", encoding="utf-8")
    summary = process_paths([str(source), str(tmp_path / "missing.txt")], str(tmp_path / "out"), progress=False)
    assert summary.failed == 1, f"total={summary.total_files}, succeeded={summary.succeeded}, failed={summary.failed}"


@pytest.mark.parametrize("workers", [1, 2])
def test_batch_output_collision_cannot_overwrite(tmp_path, workers):
    source = tmp_path / "in"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir()
    later = source / "b" / "report.txt"
    suffix = hashlib.sha1(str(later.absolute()).encode("utf-8")).hexdigest()[:8]
    (source / "a" / "report.txt").write_text("first document", encoding="utf-8")
    (source / "a" / f"report_{suffix}.txt").write_text("second document", encoding="utf-8")
    later.write_text("third document", encoding="utf-8")
    summary = process_paths([str(source)], str(tmp_path / "out"), progress=False, workers=workers)
    outputs = [row.output_path for row in summary.results]
    assert len(set(outputs)) == summary.succeeded, f"succeeded={summary.succeeded}, output paths={outputs}"
    assert {p.read_text(encoding="utf-8") for p in (tmp_path / "out").iterdir()} == {
        "first document", "second document", "third document",
    }


def test_batch_generator_include_applies_to_every_file(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    for name in ("a.txt", "b.txt"):
        (source / name).write_text("010-1234-5678 example@example.com", encoding="utf-8")
    summary = process_paths([str(source)], str(tmp_path / "out"), include=iter(["EMAIL"]), strategy="redact", progress=False)
    assert summary.succeeded == 2
    outputs = [(tmp_path / "out" / name).read_text(encoding="utf-8") for name in ("a.txt", "b.txt")]
    assert outputs[0] == outputs[1], outputs


def test_json_summary_on_vault_failure(tmp_path, capsys):
    source = tmp_path / "input.txt"
    source.write_text("010-1234-5678", encoding="utf-8")
    vault = tmp_path / "missing-parent" / "vault.json"
    try:
        code = main([str(source), "--vault", str(vault), "--json-summary"])
    except Exception as error:
        pytest.fail(f"uncaught {type(error).__name__} instead of JSON error")
    captured = capsys.readouterr()
    assert code != 0
    assert isinstance(json.loads(captured.err), dict)
    assert captured.out == ""


def test_control_valid_include_masks_phone(tmp_path, capsys):
    source = tmp_path / "input.txt"
    source.write_text("010-1234-5678", encoding="utf-8")
    assert main([str(source), "--include", "PHONE", "--json-summary"]) == 0
    assert "010-1234-5678" not in capsys.readouterr().out


def test_control_anonymizer_preserves_empty_vault():
    vault = ReversibleVault()
    result = Anonymizer(vault=vault).process("010-1234-5678")
    assert result.vault is vault
    assert len(vault) == 1


def test_control_valid_document_extracts(tmp_path):
    path = tmp_path / "valid.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", '<document><p><t>ordinary body</t></p></document>')
        archive.writestr("word/header1.xml", '<header><p><t>010-1234-5678</t></p></header>')
    document = read_text_isolated(path)
    assert "ordinary body" in document.text
    assert "010-1234-5678" in document.text


@pytest.mark.parametrize("labels", [["PHNOE"], ["PHONE", "PHNOE"], ["phone"], [], "PHONE"])
def test_invalid_filter_rejected_before_any_detector(labels, monkeypatch):
    from ko_pii.detect import detect_all

    def unexpected(*args, **kwargs):
        pytest.fail("invalid filter ran a detector")

    monkeypatch.setattr("ko_pii.detect._run_detectors", unexpected)
    with pytest.raises(ValueError):
        detect_all("synthetic", include=labels)
    with pytest.raises(ValueError):
        Anonymizer(include=labels)


@pytest.mark.parametrize("factory", [list, tuple, set, iter])
def test_filter_collections_have_same_semantics(factory):
    from ko_pii.detect import detect_all
    text = "010-1234-5678 example@example.com"
    assert {d.label for d in detect_all(text, include=factory(["EMAIL"]))} == {"EMAIL"}
    anon = Anonymizer(include=factory(["EMAIL"]))
    assert anon.process(text).text == anon.process(text).text
    assert "010-1234-5678" in anon.process(text).text


def test_empty_records_preserve_vault():
    from ko_pii.tabular import anonymize_records
    vault = ReversibleVault()
    records, actual = anonymize_records([], vault=vault)
    assert actual is vault
    assert records == []


@pytest.mark.parametrize("kind,expected", [
    ("missing", "file_unavailable"), ("glob", "glob_no_matches"),
    ("empty", "no_input_files"), ("unsupported", "unsupported_extension"),
])
def test_batch_collection_failures_are_json(tmp_path, capsys, kind, expected):
    source = tmp_path / "input"
    if kind == "glob":
        source = tmp_path / "*.txt"
    elif kind == "empty":
        source.mkdir()
    elif kind == "unsupported":
        source = source.with_suffix(".bin")
        source.write_bytes(b"synthetic")
    assert main([str(source), "--batch", "--output-dir", str(tmp_path / "out"), "--json-summary"]) == 1
    report = json.loads(capsys.readouterr().err)
    assert report["failed"] == 1
    assert report["results"][0]["error_code"] == expected


def test_allow_empty_is_explicit_and_does_not_hide_missing_file(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert process_paths([str(empty)], str(tmp_path / "out"), allow_empty=True, progress=False).failed == 0
    assert process_paths([str(tmp_path / "missing.txt")], str(tmp_path / "out"), allow_empty=True, progress=False).failed == 1


def test_json_error_reports_committed_output_without_raw_exception(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.txt"
    source.write_text("010-1234-5678", encoding="utf-8")

    def fail_report(*args, **kwargs):
        raise OSError("private exception contents")

    monkeypatch.setattr("ko_pii.cli.generate_certificate", fail_report)
    assert main([str(source), "--vault", str(tmp_path / "vault"), "--report", str(tmp_path / "report"), "--json-summary"]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["stage"] == "report_write"
    assert payload["vault_saved"] is True
    assert payload["output_state"] == "written"
    assert "private exception contents" not in captured.err
    assert "010-1234-5678" not in captured.out


def test_partial_archive_cli_exposes_coverage_not_source(tmp_path, capsys):
    path = tmp_path / "partial.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<document><t>normal</t></document>")
        archive.writestr("word/header1.xml", "<header><t>010-1234-5678")
    assert main([str(path), "--json-summary"]) == 1
    captured = capsys.readouterr()
    report = json.loads(captured.err)
    assert report["error"] == "document_extraction_incomplete"
    assert report["extraction_coverage"]["status"] == "partial"
    assert report["extraction_coverage"]["parts"][1]["status"] == "failed"
    assert captured.out == ""
    assert "010-1234-5678" not in captured.err


def test_invalid_shared_string_reference_is_not_an_empty_cell(tmp_path):
    path = tmp_path / "bad.xlsx"
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}"><si><t>normal</t></si></sst>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><row><c t="s"><v>-1</v></c></row></worksheet>')
    with pytest.raises(BoundedReadError) as error:
        read_text_isolated(path)
    assert error.value.code == "document_extraction_incomplete"


@pytest.mark.parametrize("part", ["word/header1.XML", "word/footer1.Xml"])
def test_docx_case_variant_text_parts_remain_in_coverage(tmp_path, part):
    path = tmp_path / "case-variant.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<document><t>normal</t></document>")
        archive.writestr(part, "<header><t>010-1234-5678</t></header>")
    document = read_text_isolated(path)
    assert "010-1234-5678" in document.text
    assert any(row["part"] == part and row["status"] == "read" for row in document.coverage["parts"])


def test_unknown_xml_encoding_is_recorded_as_failed_part(tmp_path):
    from ko_pii.io_.docx import inspect_text
    path = tmp_path / "unknown-encoding.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<document><t>normal</t></document>")
        archive.writestr("word/header1.xml", '<?xml version="1.0" encoding="NOT-AN-ENCODING"?><header/>')
    assert inspect_text(str(path)).coverage["status"] == "partial"
    with pytest.raises(BoundedReadError) as error:
        read_text_isolated(path)
    assert error.value.code == "document_extraction_incomplete"
    assert error.value.coverage["parts"][1]["status"] == "failed"
