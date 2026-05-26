"""정부 공문서 도메인 — 결재·보고·회의·협조 양식의 식별 필드 검출.

기본 검출기로 잡히지 않는 도메인 고유 필드:
- 문서번호 (예: ``기재부-인사-2024-00123``) — 추적자료지만 PII 결합 위험 있음
- 결재 라인 (기안/검토/협조/결재) — 인접 인명 강한 부스트 신호
- 직위·계급 + 이름 결합 — 컨텍스트 보조 신호

기본 룰 모듈에 없는 *문서번호* 만 별도 라벨로 emit. 결재라인·직위는 person.py
점수계가 이미 활용하므로 별도 emit 불필요.

Legal basis: 개인정보보호법 제2조 (문서번호 자체는 PII 아니지만, 인사 정보와
결합 시 식별 위험).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.dictionaries.agency_abbrev import is_doc_id_prefix, normalize_agency

LABEL = "DOC_ID"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "참조정보"

# 한국 정부 문서번호 — 한글기관코드 + 부서약어 + 연도 + 일련번호
# 예: 기재부-인사-2024-00123, 행안부-총무과-2025-00567
_DOC_ID = re.compile(
    r"(?<![A-Za-z0-9가-힣])"
    r"("
    r"([가-힣]{2,6})"        # 기관/부서 약어
    r"-"
    r"[가-힣A-Za-z0-9]{2,10}"  # 부서/팀
    r"-"
    r"(?:19|20)\d{2}"     # 4자리 연도
    r"-"
    r"\d{4,6}"            # 일련번호
    r")"
    r"(?![A-Za-z0-9가-힣])"
)


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _DOC_ID.finditer(text):
        prefix = m.group(2)
        # Boost confidence when prefix is a recognized agency/abbrev.
        if is_doc_id_prefix(prefix):
            confidence = 0.95
            normalized = normalize_agency(prefix) or prefix
            evidence = [
                "pattern:doc_id",
                "domain:government",
                f"agency_known:{normalized}",
            ]
        else:
            confidence = 0.85
            normalized = None
            evidence = ["pattern:doc_id", "domain:government"]
        yield DetectionResult(
            label=LABEL,
            text=m.group(1),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=confidence,
            evidence=evidence,
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "domain": "government",
                "agency_prefix": prefix,
                "agency_normalized": normalized,
            },
        )
