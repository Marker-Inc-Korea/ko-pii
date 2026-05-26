"""DOCX (Microsoft Word OOXML) 텍스트 추출 — stdlib only.

DOCX 는 ZIP + XML 구조:
  word/document.xml — 본문
  word/header*.xml — 머리말
  word/footer*.xml — 꼬리말

``<w:t>`` 요소에 텍스트가 들어 있고 ``<w:p>`` 가 문단 경계.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile


def _extract_from_xml(xml_bytes: bytes) -> list[str]:
    parts: list[str] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return parts
    for elem in root.iter():
        local = elem.tag.split("}", 1)[-1]
        if local == "t" and elem.text:
            parts.append(elem.text)
        elif local == "tab":
            parts.append("\t")
        elif local in {"br", "p"}:
            parts.append("\n")
    return parts


def _extract_metadata(xml_bytes: bytes) -> dict[str, str]:
    """docProps/core.xml 의 작성자·수정자·제목 추출."""
    meta: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return meta
    LOCAL_KEYS = {"creator", "lastModifiedBy", "title", "subject", "keywords"}
    for elem in root.iter():
        local = elem.tag.split("}", 1)[-1]
        if local in LOCAL_KEYS and elem.text:
            meta[local] = elem.text
    return meta


def read_text(path: str) -> str:
    out: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        # 메타데이터 — 작성자·수정자가 PII 인 경우가 잦음
        if "docProps/core.xml" in names:
            meta = _extract_metadata(zf.read("docProps/core.xml"))
            for key in ("creator", "lastModifiedBy", "title", "subject"):
                if key in meta:
                    out.append(f"[메타:{key}] {meta[key]}\n")
        # Main body
        candidates = ["word/document.xml"]
        # Headers / footers
        candidates += sorted(
            n for n in names
            if n.startswith("word/header") or n.startswith("word/footer")
        )
        for name in candidates:
            if name in names:
                out.extend(_extract_from_xml(zf.read(name)))
                out.append("\n")
    return "".join(out)
