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
    from ko_pii.io_.text_normalizer import normalize_for_detection

    ext = os.path.splitext(path)[1].lower()
    if ext == ".hwpx":
        raw = hwpx.read_text(path)
    elif ext == ".hwp":
        from ko_pii.io_ import hwp
        raw = hwp.read_text(path)
    elif ext == ".pdf":
        from ko_pii.io_ import pdf
        raw = pdf.read_text(path)
    elif ext == ".docx":
        raw = docx.read_text(path)
    elif ext == ".xlsx":
        raw = xlsx.read_text(path)
    elif ext in (".csv", ".tsv"):
        raw = csv_reader.read_text(path)
    else:
        raw = plain.read_text(path)
    # 셀 줄바꿈/래핑(하이픈+개행 `-\n`, 순수 개행 등)으로 쪼개진 PII 를 검출 전에
    # 복원 — *모든 포맷* 공통. 이전엔 pdf.read_text 만 적용돼 xlsx/csv/hwpx/docx
    # 에서 줄바꿈으로 분리된 RRN/전화/카드가 평문 누출됐다. (pdf 는 내부에서도
    # 적용하나 _MID_PII_NEWLINE 은 idempotent.)
    normalized, _ = normalize_for_detection(raw)
    return normalized


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
