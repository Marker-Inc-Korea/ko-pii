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

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.findall("main:si", NS):
        # 각 <si> 안의 <t> 텍스트 (rich text 면 여러 개)
        parts = []
        for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
            if t.text:
                parts.append(t.text)
        strings.append("".join(parts))
    return strings


def _cell_value(c: ET.Element, sst: list[str]) -> str:
    t_attr = c.attrib.get("t")
    if t_attr == "s":
        v = c.find("main:v", NS)
        if v is None or v.text is None:
            return ""
        try:
            return sst[int(v.text)]
        except (ValueError, IndexError):
            return ""
    if t_attr == "inlineStr":
        is_elem = c.find("main:is", NS)
        if is_elem is None:
            return ""
        return "".join(t.text or "" for t in is_elem.iter(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
    v = c.find("main:v", NS)
    return v.text if v is not None and v.text is not None else ""


def read_text(path: str) -> str:
    """탭/줄바꿈 구분된 텍스트로 모든 시트 + 셀 반환."""
    parts: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        sst = _shared_strings(zf)
        sheet_names = sorted(
            n for n in zf.namelist()
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
        for name in sheet_names:
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            for row in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                row_vals = []
                for c in row.findall("main:c", NS):
                    row_vals.append(_cell_value(c, sst))
                parts.append("\t".join(row_vals))
                parts.append("\n")
            parts.append("\n")  # sheet separator
    return "".join(parts)


def read_records(path: str) -> list[dict[str, str]]:
    """첫 행을 헤더로, 이후 행을 ``{header: value}`` dict 리스트로 반환."""
    text = read_text(path)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return []
    headers = lines[0].split("\t")
    records: list[dict[str, str]] = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        records.append(dict(zip(headers, cells[:len(headers)])))
    return records
