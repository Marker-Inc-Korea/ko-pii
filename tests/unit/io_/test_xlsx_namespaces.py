"""XLSX dialects must not be silently treated as empty worksheets."""
from html import escape
import json
import zipfile

import pytest

from ko_pii.cli import main
from ko_pii.io_ import read_records, read_text, read_text_bounded, read_text_isolated
from ko_pii.io_.coverage import DocumentExtractionError
from ko_pii.io_.xlsx import inspect_text
from ko_pii.tabular import anonymize_records


TRANSITIONAL = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
STRICT = "http://purl.oclc.org/ooxml/spreadsheetml/main"
VALUE = "first@example.com"


def element(name, body="", *, attrs="", prefix=""):
    tag = prefix + name
    return f"<{tag}{attrs}>{body}</{tag}>"


def package(path, namespace, *, shared=False, prefix="", extra_sheet=None,
            sheet_root="worksheet", shared_root="sst", shared_namespace=None):
    def xml(name, body, ns=namespace):
        declaration = f' xmlns{":" + prefix[:-1] if prefix else ""}="{escape(ns)}"' if ns else ""
        return element(name, body, attrs=declaration, prefix=prefix)

    def tag(name, body="", attrs=""):
        return element(name, body, attrs=attrs, prefix=prefix)

    values = ["email", "memo", VALUE, "public"]
    rows = []
    for index in range(2):
        cells = []
        for column in range(2):
            position = index * 2 + column
            attrs = f' r="{chr(65 + column)}{index + 1}"'
            if shared:
                cells.append(tag("c", tag("v", str(position)), attrs + ' t="s"'))
            else:
                # Rich text runs must use the selected namespace as well.
                body = tag("r", tag("t", values[position][:3])) + tag("r", tag("t", values[position][3:]))
                cells.append(tag("c", tag("is", body), attrs + ' t="inlineStr"'))
        rows.append(tag("row", "".join(cells), f' r="{index + 1}"'))
    sheet = xml(sheet_root, tag("sheetData", "".join(rows)))
    relationship_ns = ("http://purl.oclc.org/ooxml/officeDocument/relationships"
                       if namespace == STRICT else "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                         '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                         + ('<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' if shared else '')
                         + '</Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         f'<Relationship Id="rId1" Type="{relationship_ns}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{namespace}" xmlns:r="{relationship_ns}">'
                         '<sheets><sheet name="Contacts" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         f'<Relationship Id="rId1" Type="{relationship_ns}/worksheet" Target="worksheets/sheet1.xml"/>'
                         + (f'<Relationship Id="rId2" Type="{relationship_ns}/sharedStrings" Target="sharedStrings.xml"/>' if shared else '')
                         + '</Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        if shared:
            strings = "".join(tag("si", tag("r", tag("t", value[:3])) + tag("r", tag("t", value[3:]))) for value in values)
            archive.writestr("xl/sharedStrings.xml", xml(shared_root, strings, namespace if shared_namespace is None else shared_namespace))
        if extra_sheet is not None:
            archive.writestr("xl/worksheets/sheet2.xml", extra_sheet)


@pytest.mark.parametrize("namespace", [TRANSITIONAL, STRICT])
@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("prefix", ["", "s:"])
def test_namespace_preserves_cells_and_table_masking(tmp_path, namespace, shared, prefix):
    path = tmp_path / "contacts.xlsx"
    package(path, namespace, shared=shared, prefix=prefix)
    records = read_records(str(path))
    assert records == [{"email": VALUE, "memo": "public"}]
    masked, vault = anonymize_records(records)
    assert masked == [{"email": "<EMAIL_1>", "memo": "public"}]
    assert vault.reveal("<EMAIL_1>") == VALUE
    inspection = inspect_text(str(path))
    assert inspection.coverage["status"] == "complete"
    assert inspection.parts[0]["status"] == "read"
    assert inspection.text == f"email\tmemo\n{VALUE}\tpublic\n"


@pytest.mark.parametrize("reader", [read_text, read_text_bounded, read_text_isolated])
@pytest.mark.parametrize("shared", [False, True])
def test_strict_namespace_reaches_every_text_reader(tmp_path, reader, shared):
    path = tmp_path / "strict.xlsx"
    package(path, STRICT, shared=shared)
    result = reader(str(path))
    text = result if isinstance(result, str) else result.text
    assert VALUE in text


@pytest.mark.parametrize("namespace,root", [("", "worksheet"), ("urn:unsupported", "worksheet"),
                                           (TRANSITIONAL, "notWorksheet"), (STRICT, "notWorksheet")])
def test_unrecognized_worksheet_fails_instead_of_appearing_empty(tmp_path, namespace, root):
    path = tmp_path / "unknown.xlsx"
    package(path, namespace, sheet_root=root)
    with pytest.raises(ValueError):
        read_records(str(path))
    inspection = inspect_text(str(path))
    assert inspection.coverage["status"] == "failed"
    assert VALUE not in repr(inspection.coverage)
    with pytest.raises(DocumentExtractionError):
        inspection.require_complete()


@pytest.mark.parametrize("namespace,root", [("", "sst"), ("urn:unsupported", "sst"), (STRICT, "notSst")])
def test_unrecognized_string_table_is_rejected(tmp_path, namespace, root):
    path = tmp_path / "strings.xlsx"
    package(path, STRICT, shared=True, shared_namespace=namespace, shared_root=root)
    with pytest.raises(ValueError):
        read_records(str(path))
    assert inspect_text(str(path)).coverage["status"] == "failed"


def test_unknown_later_sheet_cannot_disappear_from_complete_result(tmp_path):
    path = tmp_path / "mixed.xlsx"
    package(path, TRANSITIONAL, extra_sheet='<worksheet xmlns="urn:unsupported"><sheetData/></worksheet>')
    inspection = inspect_text(str(path))
    assert VALUE in inspection.text
    assert inspection.coverage["status"] == "partial"
    with pytest.raises(DocumentExtractionError):
        inspection.require_complete()
    with pytest.raises(ValueError):
        read_records(str(path))


@pytest.mark.parametrize("namespace", [TRANSITIONAL, STRICT])
def test_valid_empty_worksheet_is_still_empty(tmp_path, namespace):
    path = tmp_path / "empty.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}"><sheetData/></worksheet>')
    assert read_records(str(path)) == []
    assert inspect_text(str(path)).parts[0]["status"] == "empty"


@pytest.mark.parametrize("namespace,success", [(STRICT, True), ("urn:unsupported", False)])
def test_cli_masks_strict_file_or_fails_without_overwriting_output(tmp_path, capsys, namespace, success):
    path = tmp_path / "input.xlsx"
    output = tmp_path / "result.txt"
    vault = tmp_path / "vault.json"
    output.write_text("previous output", encoding="utf-8")
    package(path, namespace)
    code = main([str(path), "--output", str(output), "--vault", str(vault), "--json-summary"])
    captured = capsys.readouterr()
    report = json.loads(captured.err)
    if success:
        assert code == 0
        assert "<EMAIL_1>" in output.read_text(encoding="utf-8")
        assert VALUE not in output.read_text(encoding="utf-8")
        assert vault.exists()
    else:
        assert code == 1
        assert report["error"] == "document_extraction_incomplete"
        assert output.read_text(encoding="utf-8") == "previous output"
        assert not vault.exists()


@pytest.mark.parametrize("reader", [read_text, read_text_bounded, read_text_isolated])
def test_mixed_document_is_not_reported_as_complete(tmp_path, reader):
    path = tmp_path / "mixed.xlsx"
    package(path, TRANSITIONAL, extra_sheet='<worksheet xmlns="urn:unsupported"><sheetData/></worksheet>')
    with pytest.raises(ValueError):
        reader(str(path))


def test_cli_does_not_publish_partial_document(tmp_path, capsys):
    path = tmp_path / "mixed.xlsx"
    output = tmp_path / "output.txt"
    vault = tmp_path / "vault.json"
    package(path, TRANSITIONAL, extra_sheet='<worksheet xmlns="urn:unsupported"><sheetData/></worksheet>')
    assert main([str(path), "--output", str(output), "--vault", str(vault), "--json-summary"]) == 1
    report = json.loads(capsys.readouterr().err)
    assert report["error"] == "document_extraction_incomplete"
    assert report["extraction_coverage"]["status"] == "partial"
    assert not output.exists() and not vault.exists()


@pytest.mark.parametrize("namespace", [TRANSITIONAL, STRICT])
@pytest.mark.parametrize("cell_type,value", [("str", VALUE), ("n", "123.5"), ("b", "1"), ("d", "2020-01-01")])
def test_cached_scalar_values_use_the_sheet_namespace(tmp_path, namespace, cell_type, value):
    path = tmp_path / "scalar.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}"><sheetData>'
                         '<row><c t="inlineStr"><is><t>memo</t></is></c></row>'
                         f'<row><c t="{cell_type}"><v>{value}</v></c></row></sheetData></worksheet>')
    assert read_records(str(path)) == [{"memo": value}]


@pytest.mark.parametrize("first,second", [(TRANSITIONAL, STRICT), (STRICT, TRANSITIONAL)])
def test_namespace_selection_is_per_part_not_per_workbook(tmp_path, first, second):
    path = tmp_path / "both.xlsx"
    other = f'<worksheet xmlns="{second}"><sheetData>' \
            '<row><c t="inlineStr"><is><t>email</t></is></c></row>' \
            '<row><c t="inlineStr"><is><t>second@example.com</t></is></c></row></sheetData></worksheet>'
    package(path, first, extra_sheet=other)
    assert read_records(str(path)) == [{"email": VALUE, "memo": "public"}, {"email": "second@example.com"}]
    assert "second@example.com" in read_text_bounded(path).text
