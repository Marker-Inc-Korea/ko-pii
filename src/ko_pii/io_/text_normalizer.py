"""PDF 등에서 추출된 텍스트의 불필요 줄바꿈/공백 정규화 + offset 역매핑.

PDF 텍스트 추출기는 글자 좌표 기반이라:
1. 단어/숫자 중간에 줄바꿈 삽입 (pypdf 흔함)
2. 서식 칸별 입력 시 글자 사이 공백 삽입 (주민번호: "9 5 1 2 3 0 - 1 8 5 0 4 3 1")

사용:
    normalized, offset_map = normalize_for_detection(raw_pdf_text)
    detections = detect_all(normalized)
    remapped = remap_offsets(detections, offset_map)
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ko_pii.core.types import DetectionResult

# --- 줄바꿈 정규화 패턴 ---
_MID_PII_NEWLINE = re.compile(
    r'(?<=[0-9\-])\n(?=[0-9\-])'
    r'|'
    r'(?<=[A-Za-z])\n(?=[0-9])'
    r'|'
    r'(?<=[0-9])\n(?=[A-Za-z])'
)
_MID_KOREAN_NEWLINE = re.compile(r'(?<=[가-힣])\n(?=[가-힣])')
_SOFT_LINEBREAK = re.compile(r'(?<!\n)\n(?!\n)')

# --- 칸별 공백 정규화 패턴 ---
# "9 5 1 2 3 0 - 1 8 5 0 4 3 1" → "951230-1850431"
# 공백(space)만 — 줄바꿈(\n) 제외
_SPACED_FIELD = re.compile(
    r'(?<![0-9A-Za-z\-])'
    r'([0-9A-Za-z](?: [0-9A-Za-z\-]){4,})'
    r'(?![0-9A-Za-z\-]| [0-9A-Za-z\-])'
)


def _collapse_spaced_field(text: str) -> tuple[str, list[int]]:
    """칸별 공백 패턴의 공백을 제거하고 offset 맵 반환."""
    result: list[str] = []
    offset_map: list[int] = []
    last_end = 0
    for m in _SPACED_FIELD.finditer(text):
        for i in range(last_end, m.start()):
            result.append(text[i])
            offset_map.append(i)
        span = m.group(0)
        span_start = m.start()
        for j, ch in enumerate(span):
            if ch == ' ':
                continue
            result.append(ch)
            offset_map.append(span_start + j)
        last_end = m.end()
    for i in range(last_end, len(text)):
        result.append(text[i])
        offset_map.append(i)
    return ''.join(result), offset_map


def normalize_for_detection(
    text: str,
    *,
    aggressive: bool = False,
) -> tuple[str, list[int]]:
    """PDF 추출 텍스트를 PII 검출용으로 정규화.

    Returns (normalized, offset_map).
    offset_map[i] = normalized[i]에 대응하는 원본 위치.
    """
    # Phase 1: 칸별 공백 정규화 (줄바꿈은 유지 — 토큰 경계)
    text_p1, map_p1 = _collapse_spaced_field(text)

    # Phase 2: 줄바꿈 정규화
    remove_positions: set[int] = set()
    for m in _MID_KOREAN_NEWLINE.finditer(text_p1):
        remove_positions.add(m.start())

    replace_positions: set[int] = set()
    for m in _MID_PII_NEWLINE.finditer(text_p1):
        pos = m.start()
        if pos not in remove_positions:
            replace_positions.add(pos)
    if aggressive:
        for m in _SOFT_LINEBREAK.finditer(text_p1):
            pos = m.start()
            if pos not in remove_positions and pos not in replace_positions:
                replace_positions.add(pos)

    # Phase 3: 최종 텍스트 + 원본 기준 offset 맵
    result: list[str] = []
    offset_map: list[int] = []
    for i, ch in enumerate(text_p1):
        if i in remove_positions:
            continue
        if i in replace_positions:
            result.append(' ')
            offset_map.append(map_p1[i])
            continue
        result.append(ch)
        offset_map.append(map_p1[i])
    return ''.join(result), offset_map


def remap_offsets(
    detections: list[DetectionResult],
    offset_map: list[int],
) -> list[DetectionResult]:
    """정규화 텍스트 기준 offset을 원본 텍스트 기준으로 역매핑."""
    n = len(offset_map)
    remapped: list[DetectionResult] = []
    for det in detections:
        new_start = offset_map[det.start] if det.start < n else det.start
        if det.end > 0 and det.end - 1 < n:
            new_end = offset_map[det.end - 1] + 1
        else:
            new_end = det.end
        remapped.append(replace(det, start=new_start, end=new_end))
    return remapped
