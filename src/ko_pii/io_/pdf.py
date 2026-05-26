"""PDF 텍스트 레이어 추출.

외부 의존성: ``pypdf`` (BSD-3, 가벼움). 이미지/스캔 PDF 는 OCR 필요 — 본 모듈은
*텍스트 레이어* 만 추출 (한국 공공 결재 PDF 는 대부분 텍스트 레이어 있음).

``pip install ko-pii[file]`` 로 설치.
"""
from __future__ import annotations

try:
    from pypdf import PdfReader  # type: ignore
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


def _ensure_pypdf() -> None:
    if not _HAS_PYPDF:
        raise ImportError(
            "PDF 입력은 'pypdf' 패키지가 필요합니다.\n"
            "  pip install ko-pii[file]\n"
            "또는 pip install pypdf"
        )


def read_text(path: str) -> str:
    _ensure_pypdf()
    reader = PdfReader(path)
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        parts.append(text)
        parts.append("\n\n")  # page separator
    return "".join(parts)
