"""시스템 프롬프트/지침 누출 탐지 — LLM 이 자기 시스템 프롬프트를 그대로 토해내는 경우.

두 경로: (1) context 로 시스템 프롬프트가 주어지면 출력과의 긴 substring 일치를 본다,
(2) 일반 표지(자기 지침을 1인칭으로 나열하는 문구)를 패턴으로 잡는다.
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

_LEAK_MARKERS = re.compile(
    r"(?:나의|내|제)\s*(?:시스템\s*)?(?:프롬프트|지침|규칙|역할)\s*(?:은|는|:)|"
    r"(?:받은|받았던|주어진)\s*(?:지침|지시|규칙|프롬프트|설정)\s*(?:은|는|:|을|입니다|이에요|이야)|"
    r"(?:라는|이라는)\s*(?:지침|지시|규칙|프롬프트|설정)\s*(?:을|를)?\s*받았|"
    # 1인칭 자기지침 누출의 동의어 변형(설정/구성/부여/동작원리) — 1인칭 한정으로 일반어 FP 방지
    r"(?:라고|말고|말라고)\s*(?:설정|구성|프로그래밍|세팅|훈련|설계)(?:되|됐|돼)|"
    r"(?:저의|제|나의|내)\s*(?:내부\s*)?(?:동작|작동|행동|운영|설정)\s*(?:방식|원리|원칙|규칙)\s*(?:은|는|:|을)|"
    r"(?:제가|저는|내가)\s*(?:설정|구성)된\s*(?:방식|규칙|대로)|"
    r"(?:개발자|운영자|관리자|제작자)(?:가|이|께서|는)\s*(?:저|나|제게|저에게|나에게|절|날)"
    r"[^.\n]{0,10}?(?:부여|설정|구성|지시|만들|프로그래밍|시켰)|"
    r"시스템\s*지침\s*:|위\s*지(?:시|침)\s*(?:을|를)?\s*(?:그대로\s*)?반복|"
    # 구조화 덤프(태그/키)와 자기참조 — 프롬프트 비공개/노출 언급
    r"<\s*system\s*>|[\"']?system_?prompt[\"']?\s*[:=]|"
    r"프롬프트[를을]?\s*(?:비공개|공개\s*금지|노출\s*(?:금지|하지)|유출)|"
    # 다국어 1인칭 지침 노출(일/중)
    r"私の(?:指示|システムプロンプト|ルール)|システムプロンプトを(?:公開|漏らさ|教え)|"
    r"我的(?:系统提示|指令|规则)|系统提示词|"
    r"(?:system\s*(?:prompt|프롬프트)|시스템\s*prompt|my\s*(?:instructions?|guidelines?|rules?|directives?))"
    r"\s*(?:is|are|:|을|를|알려|보여|,)?|"
    r"i'?\s*(?:was|am|m)\s*(?:told|instructed|configured|programmed|set\s*up)\s*to|"
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
