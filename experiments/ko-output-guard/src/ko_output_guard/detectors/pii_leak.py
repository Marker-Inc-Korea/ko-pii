"""PII 재누출 탐지 — ko-pii 를 재사용한다(설치돼 있으면). 출력 텍스트에 주민/카드/
전화/이메일 등 개인정보가 들어가면 누출로 본다.

ko-pii 미설치 환경에서도 import 가 실패하지 않도록 lazy + graceful 하게 처리한다.
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

# 심각도 매핑(ko-pii RiskLevel → output-guard Severity).
_RISK_TO_SEV = {"CRITICAL": Severity.CRITICAL, "HIGH": Severity.HIGH,
                "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW}

# 연결 문자열 user:pw@host — 여기 '@host' 는 이메일이 아니라 DB/서비스 호스트다.
_CONN_USERINFO = re.compile(r"[a-z][a-z0-9+.\-]*://[^\s/@]*:[^\s/@]*@[^\s/@]+")

# 출력 가드에서 제외하는 ko-pii 라벨. PERSON/ADDRESS/PERSONAL_ATTR 은 성씨-시작
# 일반명사 오탐이 잦고, MAJOR(전공)은 '의학/약학/화학' 같은 일반명사가 그대로 잡혀
# 단독으로는 개인식별이 안 되므로 결정적 PII(RRN/카드/전화/이메일/사업자 등)만 본다.
_EXCLUDE = {"PERSON", "ADDRESS", "PERSONAL_ATTR", "MAJOR"}


def scan_pii_leak(text: str) -> list[Violation]:
    try:
        from ko_pii import detect_all
    except ImportError:
        return []  # ko-pii 미설치 → PII 카테고리 비활성(다른 detector 는 계속)
    conn_spans = [(m.start(), m.end()) for m in _CONN_USERINFO.finditer(text)]
    out: list[Violation] = []
    for d in detect_all(text, exclude=_EXCLUDE):
        # 연결 문자열 내부의 '이메일'은 실제로는 호스트이므로 제외(과탐 방지).
        if d.label == "EMAIL" and any(s <= d.start < e for s, e in conn_spans):
            continue
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
    # 자리별 공백 우회('9 0 0 1 0 1 - 1 2 3 ...') 회복 — 공백 제거 사본에서 재검사한다.
    # checksum·형식 검증이 있어 임의 숫자 나열은 통과 못 한다. 사본 기준이라 offset(redact)
    # 은 못 주지만 BLOCK 자체는 유효해 누출 차단엔 충분하다.
    collapsed = re.sub(r"[ \t]+", "", text)
    if collapsed != text:
        for d in detect_all(collapsed, exclude=_EXCLUDE):
            if d.label == "EMAIL" or d.text in text:
                continue  # 이메일 오탐/원본에 그대로 있는 건 제외(중복 방지)
            risk = getattr(getattr(d, "risk_level", None), "name", "MEDIUM")
            out.append(
                Violation(
                    code=f"pii:{d.label.lower()}",
                    category=Category.PII_LEAK,
                    severity=_RISK_TO_SEV.get(risk, Severity.MEDIUM),
                    reason=f"personal data via spacing-evasion: {d.label}",
                    start=None,
                    end=None,
                    matched=d.text[:40],
                )
            )
    return out
