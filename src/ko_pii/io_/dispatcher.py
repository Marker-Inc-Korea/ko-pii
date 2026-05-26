"""확장자 기반 자동 디스패처."""
from __future__ import annotations

import os

from ko_pii.io_ import csv_reader, docx, hwpx, plain, xlsx

SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".txt", ".md", ".log",
    ".csv", ".tsv",
    ".hwpx", ".hwp",     # 한컴 (신/구)
    ".docx",
    ".xlsx",
    ".pdf",
)


def read_text(path: str) -> str:
    """파일 확장자에 따라 적절한 reader 로 텍스트를 반환.

    HWP 5.x / PDF 는 optional extras (``pip install ko-pii[file]``) 가 필요할 수
    있으며, 미설치 시 명시적 ImportError 를 발생시킨다.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".hwpx":
        return hwpx.read_text(path)
    if ext == ".hwp":
        from ko_pii.io_ import hwp
        return hwp.read_text(path)
    if ext == ".pdf":
        from ko_pii.io_ import pdf
        return pdf.read_text(path)
    if ext == ".docx":
        return docx.read_text(path)
    if ext == ".xlsx":
        return xlsx.read_text(path)
    if ext in (".csv", ".tsv"):
        return csv_reader.read_text(path)
    # 기본 plain
    return plain.read_text(path)


def read_records(path: str) -> list[dict[str, str]]:
    """CSV/TSV/XLSX 같은 표 형식만 의미가 있는 정형 reader.

    그 외 포맷은 빈 리스트 반환 — 호출자가 분기 처리.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        return csv_reader.read_records(path)
    if ext == ".xlsx":
        return xlsx.read_records(path)
    return []
