"""Common text exports must not silently change or bypass table schemas."""
import codecs
import json

import pytest

from ko_pii.batch import process_paths
from ko_pii.cli import main
from ko_pii.io_ import plain, read_records
from ko_pii.io_.bounded import BoundedReadError, read_text_bounded
from ko_pii.io_.isolated import read_text_isolated
from ko_pii.tabular import anonymize_records


EMAIL = "synthetic@example.com"


@pytest.mark.parametrize("header", ["email", '"email"', "\uc131\uba85"])
@pytest.mark.parametrize("delimiter", [",", "\t", ";", "|"])
def test_utf8_bom_does_not_hide_first_pii_column(tmp_path, header, delimiter):
    path = tmp_path / "export.csv"
    source = f"{header}{delimiter}memo\r\n{EMAIL}{delimiter}public\r\n"
    path.write_bytes(source.encode("utf-8-sig"))
    records = read_records(str(path))
    expected_header = header.strip('"')
    assert records == [{expected_header: EMAIL, "memo": "public"}]
    masked, vault = anonymize_records(records)
    assert EMAIL not in repr(masked)
    assert vault.reveal(masked[0][expected_header]) == EMAIL


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp949", "euc-kr"])
def test_supported_korean_encodings_keep_schema_and_cells(tmp_path, encoding):
    path = tmp_path / "export.tsv"
    source = "\uc131\uba85\t\uba54\ubaa8\r\n\ud64d\uae38\ub3d9\t\uc77c\ubc18 \ubb38\uc11c\r\n"
    path.write_bytes(source.encode(encoding))
    assert plain.read_text(str(path)) == source
    records = read_records(str(path))
    assert records == [{"\uc131\uba85": "\ud64d\uae38\ub3d9", "\uba54\ubaa8": "\uc77c\ubc18 \ubb38\uc11c"}]
    assert anonymize_records(records)[0][0]["\uc131\uba85"] == "<PERSON_1>"


def test_only_file_bom_is_removed_not_interior_unicode(tmp_path):
    path = tmp_path / "export.txt"
    source = "left\ufeffright\n" + EMAIL
    path.write_bytes(codecs.BOM_UTF8 + source.encode("utf-8"))
    assert plain.read_text(str(path)) == source


def test_legitimate_unicode_replacement_character_is_not_a_decode_failure(tmp_path):
    path = tmp_path / "text.txt"
    source = "literal \ufffd character"
    path.write_bytes(source.encode("utf-8"))
    assert plain.read_text(str(path)) == source


def test_cp949_extension_characters_still_decode(tmp_path):
    path = tmp_path / "text.txt"
    source = "\ub620\ubc29\uac01\ud558"
    path.write_bytes(source.encode("cp949"))
    assert plain.read_text(str(path)) == source


def test_declared_utf8_cannot_fall_back_to_a_different_encoding(tmp_path):
    path = tmp_path / "text.txt"
    path.write_bytes(codecs.BOM_UTF8 + "\ud64d\uae38\ub3d9".encode("cp949"))
    with pytest.raises(ValueError):
        plain.read_text(str(path))


@pytest.mark.parametrize("separator", ["\r", "\n", "\r\n"])
def test_valid_quoted_csv_keeps_embedded_delimiters_and_doubled_quotes(tmp_path, separator):
    path = tmp_path / "valid.csv"
    source = f'"email","memo"{separator}"{EMAIL}","a,b; c | d\t""quoted"""{separator}'
    path.write_bytes(source.encode("utf-8-sig"))
    assert read_records(str(path)) == [{"email": EMAIL, "memo": 'a,b; c | d\t"quoted"'}]


@pytest.mark.parametrize("suffix", [
    'public,"unterminated\n' + EMAIL + ",memo\n",
    'public,"quoted"unexpected\n',
])
@pytest.mark.parametrize("prefix", ["", EMAIL + ",safe\n"])
def test_malformed_csv_rejects_whole_record_set(tmp_path, prefix, suffix):
    path = tmp_path / "invalid.csv"
    path.write_text("email,memo\n" + prefix + suffix, encoding="utf-8")
    with pytest.raises(ValueError, match="CSV") as error:
        read_records(str(path))
    assert EMAIL not in str(error.value)


@pytest.mark.parametrize("payload", [b"\xff", b"\xf8", codecs.BOM_UTF8 + b"\xff"])
@pytest.mark.parametrize("reader", [plain.read_text, read_records])
def test_undecodable_file_never_returns_replacement_characters(tmp_path, payload, reader):
    path = tmp_path / "invalid.csv"
    path.write_bytes(b"email\n" + EMAIL.encode() + b"\n" + payload)
    with pytest.raises(ValueError) as error:
        reader(str(path))
    assert EMAIL not in str(error.value)


@pytest.mark.parametrize("reader", [read_text_bounded, read_text_isolated])
def test_decode_failure_has_safe_machine_readable_code(tmp_path, reader):
    path = tmp_path / "invalid.txt"
    path.write_bytes(EMAIL.encode() + b"\n\xff")
    with pytest.raises(BoundedReadError) as error:
        reader(path)
    assert error.value.code == "text_decode_failed"
    assert EMAIL not in str(error.value)


@pytest.mark.parametrize("existing_output", [False, True])
def test_cli_decode_failure_does_not_publish_output_or_vault(tmp_path, capsys, existing_output):
    source, output, vault = [tmp_path / name for name in ("in.txt", "out.txt", "vault.json")]
    source.write_bytes(EMAIL.encode() + b"\n\xff")
    if existing_output:
        output.write_text("previous result", encoding="utf-8")
    assert main([str(source), "--output", str(output), "--vault", str(vault), "--json-summary"]) == 1
    captured = capsys.readouterr()
    report = json.loads(captured.err)
    assert report["error"] == "text_decode_failed"
    assert report["output_state"] == "not_written" and report["vault_saved"] is False
    assert not captured.out and EMAIL not in captured.err
    assert not vault.exists()
    if existing_output:
        assert output.read_text(encoding="utf-8") == "previous result"
    else:
        assert not output.exists()


@pytest.mark.parametrize("workers", [1, 2])
def test_batch_reports_decode_failure_without_losing_good_output(tmp_path, workers):
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "good.txt").write_text(EMAIL, encoding="utf-8")
    (source / "bad.txt").write_bytes(EMAIL.encode() + b"\n\xff")
    output = tmp_path / "out"
    result = process_paths([str(source)], str(output), workers=workers, strategy="redact", progress=False)
    assert (result.total_files, result.succeeded, result.failed) == (2, 1, 1)
    failed = next(row for row in result.results if row.error is not None)
    assert failed.error_code == "text_decode_failed" and failed.output_path is None
    assert not (output / "bad.txt").exists()
    assert EMAIL not in (output / "good.txt").read_text(encoding="utf-8")
