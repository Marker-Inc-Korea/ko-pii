"""컨텍스트 분석 — 점수 기반 이름 탐지 + 누적 사전 + 표기 변형 매칭."""
from ko_pii.context.context_rules import NameCandidate, Score, score_candidate
from ko_pii.context.hanja import has_hanja, hanja_to_hangul
from ko_pii.context.name_dictionary import NameDictionary, NameRecord
from ko_pii.context.particles import (
    PARTICLES,
    starts_with_particle,
    strip_trailing_particle,
)
from ko_pii.context.romanization import (
    alternative_romanizations,
    romanize_name,
)

__all__ = [
    "PARTICLES",
    "strip_trailing_particle",
    "starts_with_particle",
    "NameDictionary",
    "NameRecord",
    "NameCandidate",
    "score_candidate",
    "Score",
    "hanja_to_hangul", "has_hanja",
    "romanize_name", "alternative_romanizations",
]
