"""HWPX (한컴오피스, KS X 6101) 텍스트 추출 — stdlib only.

HWPX 는 ZIP + XML 구조:
  META-INF/manifest.xml
  Contents/section0.xml, section1.xml ...
  Contents/header.xml

각 ``section*.xml`` 의 ``<hp:p>`` (문단) 아래 ``<hp:run><hp:t>...</hp:t></hp:run>``
요소에 본문 텍스트가 들어 있다. 표·머리말·꼬리말도 같은 구조라 ``<hp:t>`` 만
재귀적으로 모으면 본문 + 표 + 머리말 다 추출 가능.

References:
- https://tech.hancom.com/hwpxformat/
- KS X 6101 (OWPML)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile

from ko_pii.io_.coverage import TextExtraction, inspect_parts


_INLINE_CHARACTERS = {
    "tab": "\t", "lineBreak": "\n", "nbSpace": "\u00a0",
    "fwSpace": "\u3000", "hyphen": "\u00ad",
}


def _extract_text_from_section(xml_bytes: bytes) -> list[str]:
    parts: list[str] = []
    root = ET.fromstring(xml_bytes)
    stack = [(root, False)]
    text_depth = 0
    while stack:
        elem, closing = stack.pop()
        local = elem.tag.split("}", 1)[-1]
        if closing:
            if local == "t":
                text_depth -= 1
            # Only mixed-content tails belong to text, not XML indentation.
            if text_depth and elem.tail:
                parts.append(elem.tail)
            continue
        if local == "t":
            text_depth += 1
        if local in _INLINE_CHARACTERS:
            parts.append(_INLINE_CHARACTERS[local])
        elif local in {"p", "linesegarray"}:
            parts.append("\n")
        if text_depth and elem.text:
            parts.append(elem.text)
        # End visits retain tails in order without recursing through deep XML.
        stack.append((elem, True))
        stack.extend((child, False) for child in reversed(elem))
    return parts


def _extract_metadata(xml_bytes: bytes) -> dict[str, str]:
    """HWPX core 메타: 작성자·제목·키워드 추출."""
    meta: dict[str, str] = {}
    root = ET.fromstring(xml_bytes)
    LOCAL_KEYS = {"creator", "lastModifiedBy", "title", "subject",
                  "Author", "LastSavedBy", "Title"}
    for elem in root.iter():
        local = elem.tag.split("}", 1)[-1]
        if local in LOCAL_KEYS and elem.text:
            meta[local] = elem.text
    return meta


def inspect_text(path: str) -> TextExtraction:
    """Inspect supported text parts; partial text is for manual review only."""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        # 메타데이터 (META-INF/core.xml 또는 docInfo.xml)
        meta_candidates = [
            "META-INF/core.xml", "Contents/core.xml",
            "docProps/core.xml",
        ]
        metadata = [name for name in meta_candidates if name in names]
        section_names = sorted(
            n for n in names
            if n.startswith("Contents/section") and n.endswith(".xml")
        )
        if not section_names:
            # Some HWPX variants put sections elsewhere
            section_names = sorted(
                n for n in names
                if n.endswith(".xml") and "section" in n.lower()
            )
        if not section_names:
            section_names = ["Contents/section0.xml"]

        def read_part(archive: zipfile.ZipFile, name: str) -> str:
            if name in metadata:
                return "\n".join(f"[메타:{key}] {value}" for key, value in _extract_metadata(archive.read(name)).items())
            return "".join(_extract_text_from_section(archive.read(name)))

        return inspect_parts(zf, metadata + section_names, read_part)


def read_text(path: str) -> str:
    return inspect_text(path).require_complete()
