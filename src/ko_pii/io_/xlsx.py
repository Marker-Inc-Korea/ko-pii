"""XLSX (Microsoft Excel OOXML) 텍스트 추출 — stdlib only.

XLSX 구조:
  xl/sharedStrings.xml — 공유 문자열 표 (lookup)
  xl/worksheets/sheet1.xml ... — 셀 좌표 + 값/참조

각 ``<c>`` 셀의 ``t`` 속성:
  - ``s`` : sharedStrings 인덱스
  - ``str`` / ``inlineStr`` : 직접 문자열
  - 그 외 (숫자) : ``<v>`` 텍스트

workbook.xml의 시트 순서와 workbook.xml.rels의 시트/공유 문자열 참조를 사용한다.
테이블 분석을 위한 정형 추출 (`read_records`) + 단순 텍스트 추출 (`read_text`)을 제공한다.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
import re
from urllib.parse import unquote, urlsplit

from ko_pii.io_.coverage import TextExtraction, inspect_parts

_NAMESPACES = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/spreadsheetml/main",
)
_REL_NAMESPACES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/relationships",
)
_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_WORKBOOK = "xl/workbook.xml"
_RELS = "xl/_rels/workbook.xml.rels"


def _namespace(root: ET.Element, local_name: str) -> str:
    for namespace in _NAMESPACES:
        if root.tag == f"{{{namespace}}}{local_name}":
            return namespace
    raise ValueError("unsupported spreadsheet part root or namespace")


def _shared_strings(zf: zipfile.ZipFile, name: str | None = "xl/sharedStrings.xml") -> list[str]:
    if name is None or name not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(name))
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
    def order(name: str) -> tuple[str, int, str, str]:
        match = re.fullmatch(r"(.*sheet)([0-9]+)\.xml", name)
        if not match:
            return name, 0, "", name
        digits = match[2].lstrip("0")
        return match[1], len(digits), digits, name

    return sorted((n for n in archive.namelist()
                   if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), key=order)


def _relationship_target(item: ET.Element, names: list[str]) -> str:
    target = item.get("Target", "")
    if re.search(r"%(?![0-9a-fA-F]{2})", target):
        raise ValueError("invalid relationship target encoding")
    path = unquote(target, errors="strict")
    uri = urlsplit(path)
    if (item.get("TargetMode", "Internal") != "Internal" or not path or path.endswith("/")
            or "\\" in path or any(ord(char) < 32 for char in path)
            or uri.scheme or uri.netloc or uri.query or uri.fragment):
        raise ValueError("unsupported relationship target")
    # Resolve only ZIP member names. A leading slash is package-root relative,
    # not a host filesystem path; parent segments may not escape the package.
    pieces = [] if path.startswith("/") else ["xl"]
    for piece in path.split("/"):
        if piece in {"", "."}:
            continue
        if piece == "..":
            if not pieces:
                raise ValueError("relationship escapes package root")
            pieces.pop()
        else:
            pieces.append(piece)
    name = "/".join(pieces)
    if not name.casefold().endswith(".xml") or names.count(name) != 1:
        raise ValueError("missing, duplicate or unsupported relationship part")
    return name


def _workbook_plan(archive: zipfile.ZipFile) -> tuple[list[str], str | None]:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("duplicate spreadsheet package member")
    if _WORKBOOK not in names and _RELS not in names:
        return _sheet_names(archive), "xl/sharedStrings.xml" if "xl/sharedStrings.xml" in names else None
    if names.count(_WORKBOOK) != 1 or names.count(_RELS) != 1:
        raise ValueError("missing or duplicate workbook structure")
    workbook = ET.fromstring(archive.read(_WORKBOOK))
    namespace = _namespace(workbook, "workbook")
    relationship = _REL_NAMESPACES[_NAMESPACES.index(namespace)]
    root = ET.fromstring(archive.read(_RELS))
    if root.tag != _PACKAGE_REL + "Relationships":
        raise ValueError("unsupported workbook relationships")
    links: dict[str, ET.Element] = {}
    for link in root:
        identity = link.get("Id", "")
        if link.tag != _PACKAGE_REL + "Relationship" or not identity or identity in links:
            raise ValueError("invalid or duplicate relationship ID")
        links[identity] = link
    containers = workbook.findall(f"{{{namespace}}}sheets")
    if len(containers) != 1 or not len(containers[0]):
        raise ValueError("missing or duplicate worksheet list")
    paths: list[str] = []
    ids: set[int] = set()
    labels: set[str] = set()
    used: set[str] = set()
    for entry in containers[0]:
        identity = entry.get(f"{{{relationship}}}id", "")
        item = links.get(identity)
        number = int(entry.get("sheetId", ""))
        label = entry.get("name", "").casefold()
        if (entry.tag != f"{{{namespace}}}sheet" or item is None
                or item.get("Type") != relationship + "/worksheet"
                or number < 1 or number > 4_294_967_295 or number in ids
                or not label or label in labels or identity in used):
            raise ValueError("invalid, duplicate or unsupported worksheet reference")
        path = _relationship_target(item, names)
        if path in paths or path == _WORKBOOK:
            raise ValueError("duplicate or invalid worksheet target")
        paths.append(path)
        ids.add(number)
        labels.add(label)
        used.add(identity)
    worksheet_ids = {key for key, item in links.items() if item.get("Type") == relationship + "/worksheet"}
    if used != worksheet_ids or set(_sheet_names(archive)) - set(paths):
        raise ValueError("unlisted worksheet part")
    strings = [item for item in links.values() if item.get("Type") == relationship + "/sharedStrings"]
    if len(strings) > 1:
        raise ValueError("duplicate shared string relationships")
    shared = _relationship_target(strings[0], names) if strings else None
    if shared in paths or shared == _WORKBOOK or (
        "xl/sharedStrings.xml" in names and shared != "xl/sharedStrings.xml"
    ):
        raise ValueError("invalid or unlisted shared string table")
    return paths, shared


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
        try:
            sheet_names, strings_name = _workbook_plan(zf)
        except (ET.ParseError, ValueError, LookupError, OSError, zipfile.BadZipFile):
            return TextExtraction("", ({"part": _WORKBOOK, "status": "failed",
                                        "reason": "invalid_workbook_relationships"},))
        def read_part(archive: zipfile.ZipFile, name: str) -> str:
            nonlocal sst
            if sst is None:
                sst = _shared_strings(archive, strings_name)
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
    reader does not provide process isolation or validate all package relationships.
    """
    records: list[dict[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        try:
            names, strings_name = _workbook_plan(archive)
        except (ET.ParseError, ValueError, LookupError, OSError, zipfile.BadZipFile):
            raise ValueError("invalid workbook relationships") from None
        if not names:
            raise ValueError("spreadsheet has no supported worksheets")
        sst = _shared_strings(archive, strings_name)
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
