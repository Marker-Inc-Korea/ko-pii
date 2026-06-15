"""PII 재누출 탐지 — ko-pii 를 재사용한다(설치돼 있으면). 출력 텍스트에 주민/카드/
전화/이메일 등 개인정보가 들어가면 누출로 본다.

ko-pii 미설치 환경에서도 import 가 실패하지 않도록 lazy + graceful 하게 처리한다.
"""
from __future__ import annotations

from ..result import Category, Severity, Violation

# 심각도 매핑(ko-pii RiskLevel → output-guard Severity).
_RISK_TO_SEV = {"CRITICAL": Severity.CRITICAL, "HIGH": Severity.HIGH,
                "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW}


def scan_pii_leak(text: str) -> list[Violation]:
    try:
        from ko_pii import detect_all
    except ImportError:
        return []  # ko-pii 미설치 → PII 카테고리 비활성(다른 detector 는 계속)
    # PERSON/ADDRESS 는 ko-pii 에서 성씨-글자-시작 일반명사 오탐이 잦아 출력 가드에서는
    # 기본 제외하고 결정적 PII(RRN/카드/전화/이메일/사업자 등, checksum·형식 검증)만 본다.
    out: list[Violation] = []
    for d in detect_all(text, exclude={"PERSON", "ADDRESS", "PERSONAL_ATTR"}):
        risk = getattr(getattr(d, "risk_level", None), "name", "MEDIUM")
        out.append(
            Violation(
                code=f"pii:{d.label.lower()}",
                category=Category.PII_LEAK,
                severity=_RISK_TO_SEV.get(risk, Severity.MEDIUM),
                reason=f"personal data in output: {d.label}",
                start=d.start,
                end=d.end,
                matched=d.text[:40],
            )
        )
    return out
