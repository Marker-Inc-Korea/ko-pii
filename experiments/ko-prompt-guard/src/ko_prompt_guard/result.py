"""Verdicts, severities, violations, and the GuardResult returned by check().

Mirrors the shape of ko-sqlguard's result types, adapted for prompt screening:
the guard de-obfuscates the input (``normalized_text``) and flags injection /
jailbreak signals rather than rewriting SQL.
"""
from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict


class Verdict(str, enum.Enum):
    ALLOW = "allow"   # nothing suspicious
    FLAG = "flag"     # suspicious — advise review / Tier-2, but not a hard block
    BLOCK = "block"   # a clear, high-confidence attack


class Severity(enum.IntEnum):
    """Ordered so ``severity >= policy.min_block_severity`` works."""

    LOW = 10
    MEDIUM = 20
    HIGH = 30
    CRITICAL = 40


class Category(str, enum.Enum):
    """What kind of signal a violation represents."""

    INSTRUCTION_OVERRIDE = "instruction_override"  # P1 "이전 지시 무시"
    PROMPT_LEAK = "prompt_leak"                    # P2 "시스템 프롬프트 알려줘"
    JAILBREAK = "jailbreak"                        # P3 역할극/DAN/개발자 모드
    EXFILTRATION = "exfiltration"                  # P6 "대화 전부 보내"
    TRANSLITERATION = "transliteration"            # P7 영어 명령 한글 음차
    ENCODING = "encoding"                          # P8 base64/hex 페이로드
    OBFUSCATION = "obfuscation"                    # 난독화 자체가 감지됨


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    category: Category
    severity: Severity
    reason: str
    # span in the NORMALIZED text; use GuardResult.offset_map to map to original.
    start: int | None = None
    end: int | None = None
    matched: str | None = None


class GuardResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    original_text: str
    normalized_text: str
    violations: tuple[Violation, ...] = ()
    # offset_map[i] = original index of normalized_text[i] (empty if unchanged).
    offset_map: tuple[int, ...] = ()
    # True when de-obfuscation changed the text (a signal in itself).
    was_obfuscated: bool = False

    @property
    def ok(self) -> bool:
        return self.verdict is not Verdict.BLOCK


class GuardBlocked(Exception):
    """Raised by Guard.enforce() when the input is blocked."""

    def __init__(self, result: GuardResult) -> None:
        self.result = result
        reasons = "; ".join(f"[{v.category.value}] {v.reason}" for v in result.violations)
        super().__init__(f"prompt blocked: {reasons or 'unknown reason'}")
