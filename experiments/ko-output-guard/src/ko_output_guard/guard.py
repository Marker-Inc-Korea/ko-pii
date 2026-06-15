"""Guard: LLM 출력 안전 가드의 진입점.

check() 는 순수 함수다 — 출력 텍스트(+선택적 system-prompt context)를 받아 결정론
detector 를 돌리고 GuardResult 를 반환한다. 네트워크·LLM 호출이 없다. BLOCK 이면
위반 구간을 마스킹한 redacted_text 도 제공해 안전한 fallback 출력을 만들 수 있다.
"""
from __future__ import annotations

from collections.abc import Callable

from . import detectors
from .normalize import normalize_for_detection
from .policy import GuardPolicy
from .result import Category, GuardBlocked, GuardResult, Severity, Verdict, Violation

# 원본 텍스트 기준 offset 을 갖는(=정규화 안 거친) 카테고리만 redact 대상.
# toxicity/unsafe/prompt-leak 은 정규화본 offset 이라 원본에 적용하면 어긋난다.
_ORIGINAL_OFFSET = frozenset({Category.SECRET_LEAK, Category.PII_LEAK})


def _redact(text: str, violations: tuple[Violation, ...]) -> str:
    raw = sorted(
        (v.start, v.end) for v in violations
        if v.category in _ORIGINAL_OFFSET and v.start is not None and v.end is not None
    )
    if not raw:
        return text
    # 겹치거나 인접한 span 을 병합한다 — SECRET·PII 가 독립 검출돼 구간이 겹칠 때
    # 순차 치환이 서로의 결과를 깨뜨려(후행 바이트 재노출) 마스킹이 손상되는 것을 막는다.
    merged: list[list[int]] = [list(raw[0])]
    for s, e in raw[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out = text
    for s, e in reversed(merged):
        out = out[:s] + "[REDACTED]" + out[e:]
    return out


class Guard:
    """정책에 묶인 재사용 가능한 출력 가드. check() 호출 간 상태 없음."""

    def __init__(
        self,
        policy: GuardPolicy | None = None,
        *,
        tier2: dict[Category, Callable[[str], bool]] | None = None,
    ) -> None:
        self.policy = policy or GuardPolicy()
        # Tier-2 cascade — 카테고리별 분류기(LLM-judge/ML). 결정론이 *못 잡은* 카테고리만
        # 호출해 의미적 회색지대의 recall 을 보강한다(결정론이 잡으면 분류기 생략 → fast-path
        # 유지). 미설정({}) 이면 순수 결정론. 외부 검증에서 드러난 결정론 recall 격차용.
        self.tier2: dict[Category, Callable[[str], bool]] = tier2 or {}

    def check(self, text: str, context: str | None = None) -> GuardResult:
        if not isinstance(text, str):
            raise TypeError(f"check() expects str, got {type(text).__name__}")
        p = self.policy
        # SECRET/PII 는 형식 보존을 위해 원본에서, 한국어 detector 는 난독을 편 정규화본에서.
        norm = normalize_for_detection(text) if p.normalize else text
        violations: list[Violation] = []
        if p.detect_secret:
            violations += detectors.scan_secrets(text)
        if p.detect_pii:
            violations += detectors.scan_pii_leak(text)
        if p.detect_unsafe_advice:
            violations += detectors.scan_unsafe_advice(norm)
        if p.detect_toxicity:
            violations += detectors.scan_toxicity(norm)
        if p.detect_prompt_leak:
            violations += detectors.scan_prompt_leak(norm, context)

        # Tier-2 cascade: 결정론이 비운 카테고리만 분류기로 보강(fast-path 유지).
        if self.tier2:
            covered = {v.category for v in violations}
            for cat, clf in self.tier2.items():
                if cat in covered:
                    continue  # 이미 결정론이 잡음 → 분류기 호출 생략(비용 절감)
                probe = text if cat in (Category.SECRET_LEAK, Category.PII_LEAK) else norm
                if clf(probe):
                    violations.append(Violation(
                        code=f"{cat.value}:tier2",
                        category=cat,
                        severity=Severity.MEDIUM,
                        reason="Tier-2 classifier flagged (deterministic was SAFE)",
                    ))

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
