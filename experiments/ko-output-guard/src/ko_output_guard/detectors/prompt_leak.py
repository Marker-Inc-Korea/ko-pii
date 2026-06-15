"""시스템 프롬프트/지침 누출 탐지 — LLM 이 자기 시스템 프롬프트를 그대로 토해내는 경우.

두 경로: (1) context 로 시스템 프롬프트가 주어지면 출력과의 긴 substring 일치를 본다,
(2) 일반 표지(자기 지침을 1인칭으로 나열하는 문구)를 패턴으로 잡는다.
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

_LEAK_MARKERS = re.compile(
    r"(?:나의|내|제)\s*(?:시스템\s*)?(?:프롬프트|지침|규칙|역할)\s*(?:은|는|:)|"
    r"(?:받은|받았던|주어진)\s*(?:지침|지시|규칙|프롬프트|설정)\s*(?:은|는|:|을)|"
    r"(?:라는|이라는)\s*(?:지침|지시|규칙|프롬프트|설정)\s*(?:을|를)?\s*받았|"
    r"(?:system\s*(?:prompt|프롬프트)|시스템\s*prompt|my\s*instructions?|i\s*was\s*(?:told|instructed))\s*(?:is|are|:|을|를|알려|보여)|"
    r"다음\s*(?:지침|규칙)을?\s*따르(?:도록|라고)\s*(?:지시|설정)",
    re.IGNORECASE,
)


def _longest_common_substring_len(a: str, b: str) -> int:
    # 짧은 쪽 기준 슬라이딩(완전 LCS 는 비용 큼; 누출은 긴 연속 일치라 충분).
    if not a or not b:
        return 0
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    best = 0
    for size in range(min(len(short), 120), 14, -1):  # 20자+ 연속 일치만 관심
        for i in range(0, len(short) - size + 1):
            if short[i:i + size] in long:
                return size
    return best


def scan_prompt_leak(text: str, context: str | None = None) -> list[Violation]:
    out: list[Violation] = []
    if context:
        n = _longest_common_substring_len(text, context)
        if n >= 30:  # 시스템 프롬프트와 40자+ 연속 일치 → 누출
            out.append(
                Violation(
                    code="system_prompt_echo",
                    category=Category.PROMPT_LEAK,
                    severity=Severity.HIGH,
                    reason=f"output echoes {n}+ consecutive chars of the system prompt",
                )
            )
    m = _LEAK_MARKERS.search(text)
    if m:
        out.append(
            Violation(
                code="instruction_disclosure",
                category=Category.PROMPT_LEAK,
                severity=Severity.MEDIUM,
                reason="output discloses its own instructions/system prompt",
                start=m.start(),
                end=m.end(),
                matched=m.group(0)[:40],
            )
        )
    return out
