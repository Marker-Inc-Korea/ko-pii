"""유니코드 정규화 — 전각/호환문자 폴딩 + 보이지 않는 문자 제거 (offset 보존).

PII 검출 우회 차단:
- **전각 숫자/영문**: ``０１０`` → ``010``, ``ＡＢ`` → ``AB`` (NFKC)
- **호환 형태**: ``①`` → ``1``, ``㈜`` → ``(주)``, ``㎡`` → ``m2``
- **제로폭/보이지 않는 문자 삽입**: 제로폭 공백(U+200B), 조이너(ZWJ/ZWNJ),
  BOM(U+FEFF), 소프트하이픈(U+00AD), 방향 마크(LRM/RLM) 등 → 제거

``detect.detect_all`` 진입점에서 **기본 적용**되며, 검출 결과 offset 은
원본 문자열 기준으로 역매핑된다. 외부 의존성 없음 (표준 ``unicodedata``).

문자 단위로 처리하는 이유: 문자열 전체 NFKC 는 길이를 바꿔(``ﬁ``→``fi`` 등)
offset 이 깨진다. 글자별 폴딩 + offset_map 으로 원본 위치를 보존한다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ko_pii.core.types import DetectionResult

# 보이지 않는/제로폭/방향 문자 — 삽입형 우회 벡터.
# 소프트하이픈(00AD), 제로폭 공백·조이너·방향마크(200B–200F),
# 방향 임베딩/오버라이드/아이솔레이트·word joiner(202A–202E, 2060–206F),
# BOM/ZWNBSP(FEFF).
_INVISIBLE = re.compile(
    r"[\u00AD\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]"
)


def normalize_unicode(text: str) -> tuple[str, list[int]]:
    """NFKC 폴딩 + 보이지 않는 문자 제거.

    Returns ``(normalized, offset_map)``. ``offset_map[i]`` 는 ``normalized[i]``
    에 대응하는 원본 ``text`` 위치. 변화가 없으면 ``normalized == text`` (offset_map
    은 빈 리스트 — 호출측이 무시).
    """
    # 빠른 경로: 이미 NFKC 이고 보이지 않는 문자도 없으면 그대로 (no-op).
    if not _INVISIBLE.search(text) and unicodedata.is_normalized("NFKC", text):
        return text, []

    out: list[str] = []
    omap: list[int] = []
    for i, ch in enumerate(text):
        if _INVISIBLE.match(ch):
            continue
        for fc in unicodedata.normalize("NFKC", ch):
            out.append(fc)
            omap.append(i)
    return "".join(out), omap


def remap_to_source(
    detections: list["DetectionResult"],
    offset_map: list[int],
    source: str,
) -> list["DetectionResult"]:
    """정규화 텍스트 기준 offset 을 원본 기준으로 역매핑 + ``.text`` 원본 복원.

    ``source[start:end] == .text`` 불변식을 유지하도록 ``.text`` 를 원본
    슬라이스로 다시 설정한다.
    """
    n = len(offset_map)
    out: list[DetectionResult] = []
    for det in detections:
        start = offset_map[det.start] if det.start < n else det.start
        if det.end > 0 and det.end - 1 < n:
            end = offset_map[det.end - 1] + 1
        else:
            end = det.end
        out.append(replace(det, start=start, end=end, text=source[start:end]))
    return out
