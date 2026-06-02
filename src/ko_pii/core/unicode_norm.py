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


def _is_conjoining_jamo(ch: str) -> bool:
    """NFD \uBD84\uD574\uD615 \uD55C\uAE00 \uC790\uBAA8(\uCD08\uC131/\uC911\uC131/\uC885\uC131) \uC5EC\uBD80 \u2014 \uD569\uC131 \uD074\uB7EC\uC2A4\uD130\uC5D0 \uD3EC\uD568."""
    return (
        "\u1100" <= ch <= "\u11FF"      # Hangul Jamo
        or "\uA960" <= ch <= "\uA97F"   # Jamo Extended-A
        or "\uD7B0" <= ch <= "\uD7FF"   # Jamo Extended-B
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
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _INVISIBLE.match(ch):
            i += 1
            continue
        # 기본 문자 + 뒤따르는 결합표시/한글 자모를 한 클러스터로 묶어 NFKC.
        # 글자별 NFKC 는 NFD 분해형(예: 한글 "홍"=홍, 라틴 "é"=e+´)을 합치지
        # 못해 우회를 허용함 → 클러스터 단위 합성으로 차단. 합성 결과는 모두
        # 클러스터 시작 위치(i)로 매핑한다.
        j = i + 1
        while j < n and (unicodedata.combining(text[j]) or _is_conjoining_jamo(text[j])):
            j += 1
        for fc in unicodedata.normalize("NFKC", text[i:j]):
            out.append(fc)
            omap.append(i)
        i = j
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
        # 검출 끝 = 다음 정규화 글자의 원본 시작 위치(= 마지막 글자 클러스터의 원본 끝).
        # 합성(다대일)·제거(invisible)에도 정확하며, 0길이 검출의 start>end 역전도 방지.
        if det.end < n:
            end = offset_map[det.end]
        elif det.end == n:
            end = len(source)
        else:
            end = det.end
        out.append(replace(det, start=start, end=end, text=source[start:end]))
    return out
