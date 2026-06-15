"""Guard: 결정론 한국어 프롬프트 가드의 진입점.

check() 는 순수 함수다: 입력을 normalize() 로 난독 해제한 뒤 패턴 룰로 스캔하고
GuardResult 를 반환한다. 네트워크·LLM·임베딩 호출이 전혀 없다(그건 Tier-2 seam).
의미 기반 공격(역할극의 신종 변형 등)은 룰만으로 못 잡으므로, 보수적으로 high·
명백한 카테고리만 BLOCK 하고 나머지는 FLAG 한다(인젝션 오탐은 정상 사용자를 막는다).
"""
from __future__ import annotations

from . import patterns
from .normalize import normalize
from .normalize.leet import deleet
from .policy import GuardPolicy
from .result import GuardBlocked, GuardResult, Verdict, Violation


class Guard:
    """정책에 묶인 재사용 가능한 가드. check() 호출 간 상태 없음."""

    def __init__(self, policy: GuardPolicy | None = None) -> None:
        self.policy = policy or GuardPolicy()

    def check(self, text: str) -> GuardResult:
        if not isinstance(text, str):
            raise TypeError(f"check() expects str, got {type(text).__name__}")
        policy = self.policy
        normalized, changed = normalize(text, policy)

        violations: list[Violation] = list(patterns.scan(normalized))
        if policy.detect_encoding:
            violations.extend(patterns.scan_encoding(text))
        # leetspeak 보강: 숫자→글자 디코드본에서 '추가로' 잡히는 공격만 더한다. 원본
        # FLAG/was_obfuscated 에는 영향 없음(정상 'mp3'/'버전3' 과탐 방지).
        if policy.de_leet:
            deleeted = deleet(normalized)
            if deleeted != normalized:
                seen = {(v.category, v.code) for v in violations}
                for v in patterns.scan(deleeted):
                    if (v.category, v.code) not in seen:
                        violations.append(v)

        blocking = [
            v
            for v in violations
            if v.severity >= policy.min_block_severity and v.category in policy.block_categories
        ]
        if blocking:
            verdict = Verdict.BLOCK
        elif violations or (changed and policy.flag_pure_obfuscation):
            verdict = Verdict.FLAG
        else:
            verdict = Verdict.ALLOW

        return GuardResult(
            verdict=verdict,
            original_text=text,
            normalized_text=normalized,
            violations=tuple(violations),
            was_obfuscated=changed,
        )

    def enforce(self, text: str) -> str:
        """안전하면 (난독 해제된) 텍스트 반환, BLOCK 이면 GuardBlocked 발생."""
        result = self.check(text)
        if result.verdict is Verdict.BLOCK:
            raise GuardBlocked(result)
        return result.normalized_text


def check(text: str, policy: GuardPolicy | None = None) -> GuardResult:
    """모듈 레벨 편의 함수 — Guard(policy).check(text)."""
    return Guard(policy).check(text)
