"""한국어 유해/욕설 탐지 — 소규모 시드(실사용은 도메인 사전 확장).

명백한 욕설·혐오의 어간을 잡되, 일상어 오탐을 막기 위해 보수적으로 둔다. 변형
(ㅅㅂ 등 초성화/공백 삽입)은 호출 전 정규화(ko-prompt-guard normalize)로 펴는 것을
가정한다 — 이 모듈 자체는 clean text 의 어간 매칭만 한다.
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

# 욕설 어간(소규모 시드). 단어 경계 없이 어간 매칭(활용형 대응)하되, 흔한 합성
# 일상어(예: '병신' vs 의학용어)는 향후 화이트리스트로 분리.
_PROFANITY = re.compile(
    r"씨발|시발|씨바|개새끼|개색기|좆|병신|븅신|지랄|꺼져|엿\s*먹|닥쳐|"
    r"새끼야|개자식|미친놈|미친년|호로|쌍놈|썅|뒤져|디져|ㅅㅂ|ㅄ|ㅈㄹ|씨불|개색"
)
# 혐오/차별 표현 시드(매우 보수적 — 명백한 비하만).
_HATE = re.compile(r"틀딱|급식충|맘충|한남충|김치녀|짱깨|쪽바리|흑형|상폐녀")


def scan_toxicity(text: str) -> list[Violation]:
    out: list[Violation] = []
    for code, pat, sev in (
        ("profanity", _PROFANITY, Severity.MEDIUM),
        ("hate_speech", _HATE, Severity.HIGH),
    ):
        m = pat.search(text)
        if m:
            out.append(
                Violation(
                    code=code,
                    category=Category.TOXICITY,
                    severity=sev,
                    reason=f"toxic language in output: {code}",
                    start=m.start(),
                    end=m.end(),
                    matched=m.group(0),
                )
            )
    return out
