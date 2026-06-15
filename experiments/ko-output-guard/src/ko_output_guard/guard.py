"""Guard: LLM 출력 안전 가드의 진입점.

check() 는 순수 함수다 — 출력 텍스트(+선택적 system-prompt context)를 받아 결정론
detector 를 돌리고 GuardResult 를 반환한다. 네트워크·LLM 호출이 없다. BLOCK 이면
위반 구간을 마스킹한 redacted_text 도 제공해 안전한 fallback 출력을 만들 수 있다.
"""
from __future__ import annotations

from . import detectors
from .policy import GuardPolicy
from .result import GuardBlocked, GuardResult, Verdict, Violation


def _redact(text: str, violations: tuple[Violation, ...]) -> str:
    spans = sorted(
        ((v.start, v.end) for v in violations if v.start is not None and v.end is not None),
        reverse=True,
    )
    out = text
    for s, e in spans:
        out = out[:s] + "[REDACTED]" + out[e:]
    return out


class Guard:
    """정책에 묶인 재사용 가능한 출력 가드. check() 호출 간 상태 없음."""

    def __init__(self, policy: GuardPolicy | None = None) -> None:
        self.policy = policy or GuardPolicy()

    def check(self, text: str, context: str | None = None) -> GuardResult:
        if not isinstance(text, str):
            raise TypeError(f"check() expects str, got {type(text).__name__}")
        p = self.policy
        violations: list[Violation] = []
        if p.detect_secret:
            violations += detectors.scan_secrets(text)
        if p.detect_pii:
            violations += detectors.scan_pii_leak(text)
        if p.detect_unsafe_advice:
            violations += detectors.scan_unsafe_advice(text)
        if p.detect_toxicity:
            violations += detectors.scan_toxicity(text)
        if p.detect_prompt_leak:
            violations += detectors.scan_prompt_leak(text, context)

        blocking = [
            v for v in violations
            if v.severity >= p.min_block_severity and v.category in p.block_categories
        ]
        if blocking:
            verdict = Verdict.BLOCK
        elif violations:
            verdict = Verdict.FLAG
        else:
            verdict = Verdict.SAFE

        vt = tuple(violations)
        redacted = _redact(text, vt) if verdict is Verdict.BLOCK else None
        return GuardResult(
            verdict=verdict, original_text=text, violations=vt, redacted_text=redacted,
        )

    def enforce(self, text: str, context: str | None = None) -> str:
        """SAFE/FLAG 면 원본 반환, BLOCK 이면 GuardBlocked 발생(redacted 는 결과에)."""
        r = self.check(text, context)
        if r.verdict is Verdict.BLOCK:
            raise GuardBlocked(r)
        return text


def check(text: str, context: str | None = None, policy: GuardPolicy | None = None) -> GuardResult:
    """모듈 레벨 편의 함수 — Guard(policy).check(text, context)."""
    return Guard(policy).check(text, context)
