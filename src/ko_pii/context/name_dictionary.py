"""문서 내 누적 이름 사전.

한 번 강한 단서(직책·필드 라벨·결정적 PII 인접 등) 로 확정된 이름은
이후 약한 단서로 등장해도 다시 인식할 수 있도록 누적한다.

CLAUDE.md §2 #6 의 "컨텍스트 누적 식별" 원칙 구현.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NameRecord:
    name: str
    confidence: float
    occurrences: list[tuple[int, int]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


class NameDictionary:
    def __init__(self) -> None:
        self._names: dict[str, NameRecord] = {}

    def add(
        self,
        name: str,
        confidence: float,
        span: tuple[int, int],
        evidence: list[str] | None = None,
    ) -> NameRecord:
        rec = self._names.get(name)
        if rec is None:
            rec = NameRecord(
                name=name,
                confidence=confidence,
                occurrences=[span],
                evidence=list(evidence or []),
            )
            self._names[name] = rec
        else:
            rec.occurrences.append(span)
            # Max-confidence wins — once we've confirmed a name with strong
            # cues, weaker re-occurrences should not lower it.
            if confidence > rec.confidence:
                rec.confidence = confidence
            for e in evidence or []:
                if e not in rec.evidence:
                    rec.evidence.append(e)
        return rec

    def boost_for(self, name: str) -> float:
        rec = self._names.get(name)
        if rec is None:
            return 0.0
        # Already-confirmed names get a strong boost when scoring later
        # candidates. Capped so a single weak occurrence cannot escalate
        # the doc-level score.
        return min(0.4, rec.confidence)

    def known(self, name: str) -> bool:
        return name in self._names

    def names(self) -> list[NameRecord]:
        return list(self._names.values())

    def __len__(self) -> int:
        return len(self._names)
