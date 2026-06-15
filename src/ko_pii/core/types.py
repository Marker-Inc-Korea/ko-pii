from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class RiskLevel(IntEnum):
    INFO = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5


@dataclass
class DetectionResult:
    label: str
    text: str
    start: int
    end: int
    risk_level: RiskLevel
    confidence: float = 1.0
    evidence: list[str] = field(default_factory=list)
    legal_basis: Optional[str] = None
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def length(self) -> int:
        return self.end - self.start
