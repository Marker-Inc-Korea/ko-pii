"""XLSX (Microsoft Excel OOXML) 텍스트 추출 — stdlib only.

XLSX 구조:
  xl/sharedStrings.xml — 모든 inline strings (lookup)
  xl/worksheets/sheet1.xml ... — 셀 좌표 + 값/참조

각 ``<c>`` 셀의 ``t`` 속성:
  - ``s`` : sharedStrings 인덱스
  - ``str`` / ``inlineStr`` : 직접 문자열
  - 그 외 (숫자) : ``<v>`` 텍스트

테이블 분석을 위한 정형 추출 (`read_records`) + 단순 텍스트 추출 (`read_text`)
둘 다 제공.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator

from ko_pii.io_.coverage import TextExtraction, inspect_parts

_NAMESPACES = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/spreadsheetml/main",
)


def _namespace(root: ET.Element, local_name: str) -> str:
    for namespace in _NAMESPACES:
        if root.tag == f"{{{namespace}}}{local_name}":
            return namespace
    raise ValueError("unsupported spreadsheet part root or namespace")


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    namespace = _namespace(root, "sst")
    strings: list[str] = []
    for si in root.findall(f"{{{namespace}}}si"):
        # 각 <si> 안의 <t> 텍스트 (rich text 면 여러 개)
        parts = []
        for t in si.iter(f"{{{namespace}}}t"):
            if t.text:
                parts.append(t.text)
        strings.append("".join(parts))
    return strings


def _cell_value(c: ET.Element, sst: list[str], namespace: str) -> str:
    t_attr = c.attrib.get("t")
    if t_attr == "s":
        v = c.find(f"{{{namespace}}}v")
        if v is None or v.text is None:
            return ""
        index = int(v.text)
        if not 0 <= index < len(sst):
            raise ValueError("invalid shared string reference")
        return sst[index]
    if t_attr == "inlineStr":
        is_elem = c.find(f"{{{namespace}}}is")
        if is_elem is None:
            return ""
        return "".join(t.text or "" for t in is_elem.iter(f"{{{namespace}}}t"))
    v = c.find(f"{{{namespace}}}v")
    return v.text if v is not None and v.text is not None else ""


def _col_index(ref: str) -> int:
    """셀 참조('C5')의 0-based 열 인덱스. 참조 없으면 -1.

    빈 셀은 XML 에서 ``<c>`` 가 생략되므로, 좌표를 무시하고 순서대로 이으면
    열이 왼쪽으로 밀려 정렬이 깨진다. r 속성으로 정확한 열에 배치한다.
    """
    letters = ""
    for ch in ref:
        if ch.isalpha():
            letters += ch
        elif letters:
            break
    if not letters:
        return -1
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def _sheet_names(archive: zipfile.ZipFile) -> list[str]:
    return sorted(n for n in archive.namelist()
                  if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))


def _sheet_rows(archive: zipfile.ZipFile, name: str, sst: list[str]) -> Iterator[list[str]]:
    root = ET.fromstring(archive.read(name))
    namespace = _namespace(root, "worksheet")
    for row in root.iter(f"{{{namespace}}}row"):
        cells: dict[int, str] = {}
        seq = -1
        for cell in row.findall(f"{{{namespace}}}c"):
            column = _col_index(cell.attrib.get("r", ""))
            if column < 0:
                column = seq + 1
            if column >= 16_384:
                raise ValueError("column reference exceeds spreadsheet limits")
            if column in cells:
                raise ValueError("duplicate cell reference")
            seq = max(seq, column)
            cells[column] = _cell_value(cell, sst, namespace)
        yield [cells.get(index, "") for index in range(seq + 1)]


def inspect_text(path: str) -> TextExtraction:
    """Inspect each sheet without silently dropping parse failures."""
    with zipfile.ZipFile(path, "r") as zf:
        sst: list[str] | None = None
        sheet_names = _sheet_names(zf)
        def read_part(archive: zipfile.ZipFile, name: str) -> str:
            nonlocal sst
            if sst is None:
                sst = _shared_strings(archive)
            return "".join("\t".join(row) + "\n" for row in _sheet_rows(archive, name, sst))

        return inspect_parts(zf, sheet_names, read_part)


def read_text(path: str) -> str:
    """탭/줄바꿈 구분된 텍스트로 모든 시트 + 셀 반환."""
    return inspect_text(path).require_complete()


def read_records(path: str) -> list[dict[str, str]]:
    """Read each sheet using its own first nonempty row as headers.

    Cell strings are preserved, including tabs/newlines. Duplicate/blank headers
    and nonempty cells beyond the headers are rejected, never silently dropped.
    Empty rows and trailing empty formatting cells are ignored. This low-level
    reader does not provide process isolation or validate package relationships.
    """
    records: list[dict[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        names = _sheet_names(archive)
        if not names:
            raise ValueError("spreadsheet has no supported worksheets")
        sst = _shared_strings(archive)
        for name in names:
            headers: list[str] | None = None
            for cells in _sheet_rows(archive, name, sst):
                if not any(value.strip() for value in cells):
                    continue
                if headers is None:
                    # OOXML may include trailing cells solely for formatting.
                    while cells and cells[-1] == "":
                        cells.pop()
                    if any(not key.strip() for key in cells) or len(set(cells)) != len(cells):
                        raise ValueError("spreadsheet headers must be nonempty and unique")
                    headers = cells
                    continue
                if any(value != "" for value in cells[len(headers):]):
                    raise ValueError("spreadsheet row has values beyond its headers")
                values = cells[:len(headers)] + [""] * max(0, len(headers) - len(cells))
                records.append(dict(zip(headers, values)))
    return records
