"""PDF 텍스트 레이어 추출.

파서 우선순위: pdfplumber (레이아웃 분석 우수) > pypdf (fallback).
이미지/스캔 PDF 는 OCR 필요 — 본 모듈은 *텍스트 레이어* 만 추출
(한국 공공 결재 PDF 는 대부분 텍스트 레이어 있음).

``pip install ko-pii[file]`` 로 설치.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

try:
    import pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


def _ensure_pdf_lib() -> None:
    if not _HAS_PDFPLUMBER and not _HAS_PYPDF:
        raise ImportError(
            "PDF 입력은 'pdfplumber' 또는 'pypdf' 패키지가 필요합니다.\n"
            "  pip install ko-pii[file]\n"
            "또는 pip install pdfplumber"
        )


@dataclass(frozen=True)
class PdfTextResult:
    """Text-layer coverage only; embedded images are not inspected with OCR."""
    text: str
    page_count: int
    failed_pages: tuple[int, ...]
    empty_pages: tuple[int, ...]


class PdfExtractionError(ValueError):
    code = "pdf_extraction_incomplete"

    def __init__(self, result: PdfTextResult) -> None:
        self.page_count = result.page_count
        self.failed_pages = result.failed_pages
        self.empty_pages = result.empty_pages
        # Keep extracted text and parser exceptions out of error messages.
        super().__init__(
            f"PDF text extraction incomplete: pages={result.page_count}, "
            f"failed_pages={list(result.failed_pages)}, "
            f"empty_pages={list(result.empty_pages)}; review the source or apply OCR"
        )


def _collect_pages(pages: Iterable[Any]) -> PdfTextResult:
    parts = []
    failed = []
    empty = []
    for number, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            failed.append(number)
            text = ""
        else:
            if not text.strip():
                empty.append(number)
        parts.append(text)
    return PdfTextResult("\n\n".join(parts), len(parts), tuple(failed), tuple(empty))


def inspect_text(path: str) -> PdfTextResult:
    """Return partial text and coverage for an explicit manual-review workflow."""
    _ensure_pdf_lib()
    if _HAS_PDFPLUMBER:
        with pdfplumber.open(path) as pdf:
            return _collect_pages(pdf.pages)
    reader = PdfReader(path)
    return _collect_pages(reader.pages)


def _extract_raw(path: str) -> str:
    result = inspect_text(path)
    if not result.page_count or result.failed_pages or result.empty_pages:
        raise PdfExtractionError(result)
    return result.text


def read_text(path: str, *, normalize: bool = True) -> str:
    """PDF 텍스트 레이어 추출.

    Parameters
    ----------
    normalize : bool
        True(기본)이면 PII 패턴 중간의 불필요 줄바꿈/공백을 정규화.
        PDF 특성상 단어/숫자 중간에 줄바꿈·칸별 공백이 삽입되어
        PII 검출이 실패하는 경우가 많으므로 기본 활성화.
    """
    _ensure_pdf_lib()
    raw = _extract_raw(path)
    if normalize:
        from ko_pii.io_.text_normalizer import normalize_for_detection
        normalized, _ = normalize_for_detection(raw)
        return normalized
    return raw


def read_text_with_map(path: str) -> tuple[str, str, list[int]]:
    """PDF 텍스트 추출 + offset 역매핑 정보.

    Returns
    -------
    (raw, normalized, offset_map)
        raw : 원본 PDF 추출 텍스트
        normalized : 정규화된 텍스트 (PII 검출용)
        offset_map : normalized[i] → raw[offset_map[i]]
    """
    _ensure_pdf_lib()
    raw = _extract_raw(path)
    from ko_pii.io_.text_normalizer import normalize_for_detection
    normalized, offset_map = normalize_for_detection(raw)
    return raw, normalized, offset_map
