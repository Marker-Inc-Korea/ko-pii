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
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit

from ko_pii.io_.coverage import TextExtraction, inspect_parts


_INLINE_CHARACTERS = {
    "tab": "\t", "lineBreak": "\n", "nbSpace": "\u00a0",
    "fwSpace": "\u3000", "hyphen": "\u00ad",
}
_CONTENT = "Contents/content.hpf"
_OPF_NAMESPACES = {"http://www.idpf.org/2007/opf/", "http://www.idpf.org/2007/opf"}
_SECTION = "{http://www.hancom.co.kr/hwpml/2011/section}sec"
_HEAD = "{http://www.hancom.co.kr/hwpml/2011/head}head"


def _extract_text_from_section(xml_bytes: bytes) -> list[str]:
    return _section_parts(ET.fromstring(xml_bytes))


def _section_parts(root: ET.Element) -> list[str]:
    parts: list[str] = []
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


def _section_sort_key(name: str) -> tuple[str, int, str, str]:
    match = re.fullmatch(r"(.*section)([0-9]+)\.xml", name)
    if not match:
        return name, 0, "", name
    digits = match[2].lstrip("0")
    return match[1], len(digits), digits, name


def _discovered_sections(names: list[str]) -> list[str]:
    sections = [n for n in names if n.startswith("Contents/section") and n.endswith(".xml")]
    if not sections:
        sections = [n for n in names if n.endswith(".xml") and "section" in n.lower()]
    return sorted(sections, key=_section_sort_key)


def _local_manifest_path(href: str, names: list[str]) -> str:
    path = unquote(href, errors="strict")
    parsed = urlsplit(path)
    if (not path or path.startswith("/") or path.endswith("/") or "\\" in path
            or any(ord(char) < 32 for char in path)
            or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            or ".." in PurePosixPath(path).parts):
        raise ValueError("unsupported package path")
    name = str(PurePosixPath(path))
    relative = str(PurePosixPath("Contents") / name)
    if name in names and relative in names and name != relative:
        raise ValueError("ambiguous package path")
    # Hancom writes archive-root paths; accept unambiguous package-relative paths too.
    result = name if name.startswith("Contents/") or name in names else relative
    if names.count(result) > 1:
        raise ValueError("duplicate package member")
    return result


def _content_plan(archive: zipfile.ZipFile, names: list[str]) -> tuple[str, list[str]]:
    if names.count(_CONTENT) != 1:
        raise ValueError("duplicate content manifest")
    root = ET.fromstring(archive.read(_CONTENT))
    namespace = root.tag.removesuffix("}package").removeprefix("{")
    if namespace not in _OPF_NAMESPACES or root.tag != f"{{{namespace}}}package":
        raise ValueError("unsupported content manifest")
    ns = f"{{{namespace}}}"
    manifests, spines = root.findall(ns + "manifest"), root.findall(ns + "spine")
    if len(manifests) != 1 or len(spines) != 1:
        raise ValueError("missing or duplicate package structure")
    if any(item.tag != ns + "item" for item in manifests[0]) or any(
        item.tag != ns + "itemref" for item in spines[0]
    ):
        raise ValueError("unsupported manifest or spine entry")
    items: dict[str, ET.Element] = {}
    for item in manifests[0].findall(ns + "item"):
        identity = item.get("id", "")
        if not identity or identity in items:
            raise ValueError("missing or duplicate manifest ID")
        items[identity] = item
    paths: list[str] = []
    for reference in spines[0].findall(ns + "itemref"):
        item = items[reference.get("idref", "")]
        if item.get("media-type", "application/xml") not in {"application/xml", "text/xml"}:
            raise ValueError("unsupported spine content type")
        path = _local_manifest_path(item.get("href", ""), names)
        if path == _CONTENT or path in paths:
            raise ValueError("duplicate spine part")
        paths.append(path)
    if not paths or set(_discovered_sections(names)) - set(paths):
        raise ValueError("missing or unreferenced body sections")

    fields = {"title", "creator", "subject", "description", "lastsaveby", "keyword"}
    metadata = []
    for container in root.findall(ns + "metadata"):
        for element in container:
            local = element.tag.split("}", 1)[-1]
            key = element.get("name", "").lower() if element.tag == ns + "meta" else local.lower()
            if key in fields and element.tag.startswith((ns, "{http://purl.org/dc/elements/1.1/}")):
                value = "".join(element.itertext())
                if value.strip():
                    metadata.append(f"[메타:{key}] {value}")
    return "\n".join(metadata), paths


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
        has_manifest = _CONTENT in names
        manifest_text = ""
        if has_manifest:
            try:
                manifest_text, section_names = _content_plan(zf, names)
                if set(section_names) & set(metadata):
                    raise ValueError("metadata cannot be a body part")
            except (ET.ParseError, ValueError, LookupError, OSError, zipfile.BadZipFile):
                return TextExtraction("", ({"part": _CONTENT, "status": "failed",
                                            "reason": "invalid_content_manifest"},))
            metadata.insert(0, _CONTENT)
        else:
            section_names = _discovered_sections(names) or ["Contents/section0.xml"]
        body_seen = False

        def read_part(archive: zipfile.ZipFile, name: str) -> str:
            nonlocal body_seen
            if name == _CONTENT:
                return manifest_text
            if name in metadata:
                return "\n".join(f"[메타:{key}] {value}" for key, value in _extract_metadata(archive.read(name)).items())
            root = ET.fromstring(archive.read(name))
            if has_manifest:
                if root.tag == _HEAD:
                    return ""
                if root.tag != _SECTION:
                    raise ValueError("unsupported spine part root")
            body_seen = True
            return "".join(_section_parts(root))

        result = inspect_parts(zf, metadata + section_names, read_part)
        if has_manifest and not body_seen:
            return TextExtraction(result.text, result.parts + ({"part": "(body)", "status": "failed",
                                                               "reason": "missing_body_sections"},))
        return result


def read_text(path: str) -> str:
    return inspect_text(path).require_complete()
