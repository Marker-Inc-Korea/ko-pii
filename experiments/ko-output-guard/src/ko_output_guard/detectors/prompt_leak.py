"""시스템 프롬프트/지침 누출 탐지 — LLM 이 자기 시스템 프롬프트를 그대로 토해내는 경우.

두 경로: (1) context 로 시스템 프롬프트가 주어지면 출력과의 긴 substring 일치를 본다,
(2) 일반 표지(자기 지침을 1인칭으로 나열하는 문구)를 패턴으로 잡는다.
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

# 1인칭 앵커 — 자기지침 노출만 잡고, 구조화 키/태그(정상 설정·문서와 구분 불가)는
# 의도적으로 보지 않는다(그건 Tier-2 영역). 1인칭 한정이라 일반어 FP 위험이 낮다.
_FP = r"(?:나의|내|제|저의|저는|제가|내가)"
# 강한 노출 신호 명사 — 1인칭+주제격만으로도 자기지침 노출로 본다.
_STRONG = (
    r"(?:시스템\s*)?(?:프롬프트|지침|지시|시스템\s*메시지|초기\s*명령|내장\s*규정|"
    r"행동\s*강령|운영\s*정책|SOP|"
    r"instructions?|system\s*message|prompt|directives?|"
    r"指示|システムプロンプト|系统提示|系統提示|提示词|指令)"
)
# 약한 명사 — '규칙/방침/역할'처럼 일상에도 흔해, 노출동사가 함께일 때만 본다(FP 방지).
_WEAK = (
    r"(?:규칙|규정|방침|수칙|준칙|지령|계명|철칙|원칙|가이드라인|매뉴얼|프로토콜|"
    r"세팅|환경설정|구성값|파라미터|역할|페르소나|행동\s*수칙|guidelines?|rules?|方针|方針|规则|ルール)"
)
_LEAK_MARKERS = re.compile(
    # 1인칭 + 강한명사 + 주제격(규칙 나열 시작)
    rf"{_FP}\s*{_STRONG}\s*(?:은|는|도|만|이라고|입니다|이에요|이야|:|=|는요)|"
    # 1인칭 + (강한|약한)명사 + 목적격(을/를) + 노출동사
    rf"{_FP}\s*(?:{_STRONG}|{_WEAK})\s*(?:을|를)\s*[^.\n]{{0,8}}?"
    r"(?:알려|말씀|공개|요약|풀어|밝히|설명|적|반복|옮기|노출)|"
    # 받은/주어진/부여받은 + 강한명사
    rf"(?:받은|받았던|주어진|부여받은|내려받은)\s*{_STRONG}\s*(?:은|는|:|을|를|대로|에\s*따라|입니다|이에요)|"
    rf"(?:라는|이라는)\s*{_STRONG}\s*(?:을|를)?\s*받았|"
    # 1인칭 + 동작/작동/운영 원리·방식
    rf"{_FP}\s*(?:내부\s*)?(?:동작|작동|행동|운영|설정)\s*(?:방식|원리|원칙)\s*(?:은|는|:|을)|"
    r"(?:제가|저는|내가)\s*(?:설정|구성)된\s*(?:방식|규칙|대로)|"
    # …라고 설정/구성됨(종결 한정 — '되면' 같은 조건절 제외)
    r"(?:라고|말고|말라고)\s*(?:설정|구성|프로그래밍|세팅|훈련|설계)(?:되었|됐|돼\s*있|된\s*상태|되어\s*있)|"
    # 개발자/운영자가 (나에게) 부여/구성
    r"(?:개발자|운영자|관리자|제작자)(?:가|이|께서|는)\s*(?:저|나|제게|저에게|나에게|절|날)"
    r"[^.\n]{0,10}?(?:부여|설정|구성|지시|만들|프로그래밍|시켰|내려준|주입)|"
    # 시스템 지침 라벨 / 위 지시·규정 반복·재출력
    r"시스템\s*지침\s*:|위\s*(?:지시|지침|규칙|규정|방침)\s*(?:을|를)?\s*(?:그대로\s*)?(?:반복|옮기|재출력)|"
    # 프롬프트 비공개/노출 자기참조
    r"프롬프트[를을]?\s*(?:비공개|공개\s*금지|노출\s*(?:금지|하지)|유출|숨기|숨김)|"
    # 영문: reveal/disclose my (system prompt|instructions) / my system prompt is·says
    r"(?:reveal|disclose|show|repeat|share)\s+(?:my|the|your)\s+(?:system\s*prompt|instructions?|rules?)|"
    r"my\s+system\s*(?:prompt|message)\s*(?:is|says|:)|"
    r"i'?\s*(?:was|am|m)\s*(?:told|instructed|configured|programmed|set\s*up)\s*to|"
    # 일/중 1인칭(bare 系统提示词 류 교육 설명 FP 는 제외)
    r"私の(?:指示|システムプロンプト|ルール|方針)|システムプロンプトを(?:公開|漏らさ|教え)|"
    r"我的(?:系统提示|指令|规则|方针)|"
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
