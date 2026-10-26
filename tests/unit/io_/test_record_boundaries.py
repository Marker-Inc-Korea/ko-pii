"""Table readers must not reinterpret or silently discard source cells."""
from html import escape
import zipfile

import pytest

from ko_pii.io_ import read_records
from ko_pii.tabular import anonymize_records


def spreadsheet(path, sheets):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path, "w") as archive:
        for index, rows in enumerate(sheets, 1):
            content = []
            for number, row in enumerate(rows, 1):
                cells = []
                for column, value in enumerate(row):
                    value = escape(value).replace("\r", "&#13;")
                    cells.append(f'<c r="{chr(65 + column)}{number}" t="inlineStr">'
                                 f'<is><t xml:space="preserve">{value}</t></is></c>')
                content.append(f'<row r="{number}">{"".join(cells)}</row>')
            archive.writestr(f"xl/worksheets/sheet{index}.xml",
                             f'<worksheet xmlns="{ns}"><sheetData>{"".join(content)}</sheetData></worksheet>')


def test_headers_are_independent_per_sheet(tmp_path):
    path = tmp_path / "sheets.xlsx"
    spreadsheet(path, [
        [["email", "memo"], ["first@example.com", "public"]],
        [["memo", "email"], ["public", "second@example.com"]],
    ])
    records = read_records(str(path))
    assert records == [{"email": "first@example.com", "memo": "public"},
                       {"memo": "public", "email": "second@example.com"}]
    masked, _ = anonymize_records(records)
    assert "@example.com" not in repr(masked)
    assert records[1]["email"] == "second@example.com"


@pytest.mark.parametrize("separator", ["\t", "\n", "\r\n"])
def test_cell_delimiters_and_whitespace_are_preserved(tmp_path, separator):
    path = tmp_path / "cells.xlsx"
    value = " first@example.com" + separator + "second@example.com "
    spreadsheet(path, [[["email", "memo"], [value, "public"]]])
    records = read_records(str(path))
    assert records == [{"email": value, "memo": "public"}]
    masked, vault = anonymize_records(records)
    assert vault.reveal(masked[0]["email"]) == value


@pytest.mark.parametrize("headers", [["email", "email"], ["", "email"], ["email", "   "]])
@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_ambiguous_headers_fail_without_reflecting_content(tmp_path, headers, kind):
    path = tmp_path / ("ambiguous." + kind)
    if kind == "xlsx":
        spreadsheet(path, [[headers, ["first@example.com", "second@example.com"]]])
    else:
        path.write_text(",".join(headers) + "\nfirst@example.com,second@example.com\n", encoding="utf-8")
    with pytest.raises(ValueError, match="headers") as error:
        read_records(str(path))
    assert "@example.com" not in str(error.value)


@pytest.mark.parametrize("extra", ["second@example.com", " "])
def test_xlsx_nonempty_overflow_is_rejected(tmp_path, extra):
    path = tmp_path / "overflow.xlsx"
    spreadsheet(path, [[["email"], ["first@example.com", extra]]])
    with pytest.raises(ValueError, match="beyond its headers"):
        read_records(str(path))


def test_xlsx_empty_rows_missing_cells_and_formatting_cells(tmp_path):
    path = tmp_path / "empty.xlsx"
    spreadsheet(path, [[], [[], ["email", "memo", ""], [], ["first@example.com"],
                           ["second@example.com", "public", ""]]])
    assert read_records(str(path)) == [{"email": "first@example.com", "memo": ""},
                                      {"email": "second@example.com", "memo": "public"}]


def test_bad_later_sheet_raises_instead_of_returning_partial_records(tmp_path):
    path = tmp_path / "partial.xlsx"
    spreadsheet(path, [[["email"], ["first@example.com"]], [["email", "email"]]])
    with pytest.raises(ValueError, match="headers"):
        read_records(str(path))


def test_duplicate_cell_reference_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "duplicate-cell.xlsx"
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData>'
                         '<row><c r="A1" t="inlineStr"><is><t>email</t></is></c></row>'
                         '<row><c r="A2" t="inlineStr"><is><t>first@example.com</t></is></c>'
                         '<c r="A2" t="inlineStr"><is><t>public</t></is></c></row>'
                         '</sheetData></worksheet>')
    with pytest.raises(ValueError, match="duplicate cell reference"):
        read_records(str(path))


def test_csv_overflow_retains_legacy_restkey_and_gets_screened(tmp_path):
    path = tmp_path / "overflow.csv"
    path.write_text("email,memo\nfirst@example.com,public,second@example.com\n", encoding="utf-8")
    records = read_records(str(path))
    assert records[0][None] == ["second@example.com"]
    masked, _ = anonymize_records(records)
    assert "@example.com" not in repr(masked)


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_csv_quoted_newline_stays_in_one_cell(tmp_path, separator):
    path = tmp_path / "quoted.csv"
    value = "first@example.com" + separator + "second@example.com"
    path.write_bytes(('email,memo\r\n"' + value + '",public\r\n').encode("utf-8"))
    assert read_records(str(path)) == [{"email": value, "memo": "public"}]
