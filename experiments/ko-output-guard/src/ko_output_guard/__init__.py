"""ko-output-guard — 결정론 한국어 LLM 출력 안전 가드.

입력 가드(ko-prompt-guard)의 대칭. LLM 출력에서 크리덴셜/PII 누출, 식약처 도메인
위험 권고, 유해 표현, 시스템 프롬프트 누출을 잡는다. 순수·결정론(네트워크/LLM 없음).

    from ko_output_guard import Guard
    r = Guard().check(llm_output, context=system_prompt)
    if r.verdict is not Verdict.SAFE:
        ...  # r.violations, r.redacted_text
"""
from __future__ import annotations

from .guard import Guard, check
from .policy import GuardPolicy
from .result import Category, GuardBlocked, GuardResult, Severity, Verdict, Violation

__version__ = "0.1.0"
__all__ = [
    "Guard", "check", "GuardPolicy", "GuardResult", "GuardBlocked",
    "Verdict", "Category", "Severity", "Violation",
]
