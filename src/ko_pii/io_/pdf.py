"""PDF 텍스트 레이어 추출.

파서 우선순위: pdfplumber (레이아웃 분석 우수) > pypdf (fallback).
이미지/스캔 PDF 는 OCR 필요 — 본 모듈은 *텍스트 레이어* 만 추출
(한국 공공 결재 PDF 는 대부분 텍스트 레이어 있음).

``pip install ko-pii[file]`` 로 설치.
"""
from __future__ import annotations

try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader  # type: ignore
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


def _extract_raw(path: str) -> str:
    """PDF → 원본 텍스트 추출 (pdfplumber 우선, pypdf fallback)."""
    if _HAS_PDFPLUMBER:
        parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                parts.append(text)
        return "\n\n".join(parts)

    # fallback: pypdf
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        parts.append(text)
    return "\n\n".join(parts)


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
