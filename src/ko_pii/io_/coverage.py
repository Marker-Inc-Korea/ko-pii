"""Content-free coverage of supported archive text parts, not OCR coverage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import xml.etree.ElementTree as ET
import zipfile


@dataclass(frozen=True)
class TextExtraction:
    text: str
    parts: tuple[dict[str, str], ...]

    @property
    def coverage(self) -> dict[str, object]:
        failed = sum(part["status"] == "failed" for part in self.parts)
        return {
            "status": "partial" if failed and self.text.strip() else "failed" if failed else "complete",
            "scope": "discovered_supported_text_parts",
            "parts": list(self.parts),
            "limitations": [
                "embedded_images_not_ocr_checked", "unsupported_parts_not_inspected",
                "package_relationships_not_validated",
            ],
        }

    def require_complete(self) -> str:
        if not self.parts or any(part["status"] == "failed" for part in self.parts):
            raise DocumentExtractionError(self.coverage)
        return self.text


class DocumentExtractionError(ValueError):
    code = "document_extraction_incomplete"

    def __init__(self, coverage: dict[str, object]) -> None:
        self.coverage = coverage
        super().__init__("document text extraction incomplete; review failed parts")


def inspect_parts(
    archive: zipfile.ZipFile,
    names: list[str],
    reader: Callable[[zipfile.ZipFile, str], str],
) -> TextExtraction:
    chunks: list[str] = []
    parts: list[dict[str, str]] = []
    for name in names:
        try:
            text = reader(archive, name)
        except (ET.ParseError, ValueError, LookupError, OSError, zipfile.BadZipFile):
            parts.append({"part": name, "status": "failed", "reason": "part_parse_failed"})
        else:
            chunks.append(text)
            parts.append({"part": name, "status": "read" if text.strip() else "empty"})
    if not names:
        parts.append({"part": "(document)", "status": "failed", "reason": "missing_text_parts"})
    return TextExtraction("\n".join(chunks), tuple(parts))
