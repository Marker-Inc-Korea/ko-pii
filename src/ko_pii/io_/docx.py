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

from ko_pii.io_.coverage import TextExtraction, inspect_parts


def _extract_from_xml(xml_bytes: bytes) -> list[str]:
    parts: list[str] = []
    root = ET.fromstring(xml_bytes)
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
    root = ET.fromstring(xml_bytes)
    LOCAL_KEYS = {"creator", "lastModifiedBy", "title", "subject", "keywords"}
    for elem in root.iter():
        local = elem.tag.split("}", 1)[-1]
        if local in LOCAL_KEYS and elem.text:
            meta[local] = elem.text
    return meta


def inspect_text(path: str) -> TextExtraction:
    """Inspect supported text parts; partial text is for manual review only."""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        candidates = ["word/document.xml"]
        if "docProps/core.xml" in names:
            candidates.insert(0, "docProps/core.xml")
        candidates += sorted(
            n for n in names
            if (n.startswith("word/header") or n.startswith("word/footer")) and n.casefold().endswith(".xml")
        )

        def read_part(archive: zipfile.ZipFile, name: str) -> str:
            if name == "docProps/core.xml":
                return "\n".join(f"[메타:{key}] {value}" for key, value in _extract_metadata(archive.read(name)).items())
            return "".join(_extract_from_xml(archive.read(name)))

        return inspect_parts(zf, candidates, read_part)


def read_text(path: str) -> str:
    return inspect_text(path).require_complete()
