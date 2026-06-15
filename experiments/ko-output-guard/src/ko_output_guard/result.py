"""결과 타입 — Verdict / Category / Severity / Violation / GuardResult.

ko-prompt-guard 와 동일한 모양(결정론·pydantic·frozen)을 따른다. 출력 가드는
입력 가드의 대칭이므로 API 표면을 일부러 닮게 유지한다.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class Verdict(str, Enum):
    SAFE = "safe"      # 내보내도 안전
    FLAG = "flag"      # 의심 — 사람 검토/로깅 권고
    BLOCK = "block"    # 명백 — 내보내기 차단


class Category(str, Enum):
    SECRET_LEAK = "secret_leak"      # API key/토큰/private key 등 크리덴셜
    PII_LEAK = "pii_leak"            # 개인정보 재누출(ko-pii 연동)
    UNSAFE_ADVICE = "unsafe_advice"  # 식약처 도메인 위험 권고
    TOXICITY = "toxicity"            # 욕설/혐오/유해 표현
    PROMPT_LEAK = "prompt_leak"      # 시스템 프롬프트/지침 그대로 출력


class Severity(int, Enum):
    LOW = 10
    MEDIUM = 20
    HIGH = 30
    CRITICAL = 40

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Severity):
            return self.value < other.value
        return NotImplemented


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    category: Category
    severity: Severity
    reason: str
    start: int | None = None
    end: int | None = None
    matched: str | None = None


class GuardResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    original_text: str
    violations: tuple[Violation, ...] = ()
    # 가장 안전한 출력형: BLOCK 사유를 마스킹한 텍스트(없으면 None).
    redacted_text: str | None = None

    @property
    def is_safe(self) -> bool:
        return self.verdict is Verdict.SAFE


class GuardBlocked(Exception):
    """enforce() 가 BLOCK 출력에 대해 발생시키는 예외."""

    def __init__(self, result: GuardResult) -> None:
        self.result = result
        cats = ", ".join(sorted({v.category.value for v in result.violations}))
        super().__init__(f"output blocked: {cats}")
