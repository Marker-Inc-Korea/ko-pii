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
# 일반명사 오탐이 잦고, MAJOR(전공)은 '의학/약학/화학', AGE('두 살')는 맥락 의존
# 일반표현이라 단독으로는 식별이 안 되므로 결정적 PII(RRN/카드/전화/이메일/사업자)만 본다.
_EXCLUDE = {"PERSON", "ADDRESS", "PERSONAL_ATTR", "MAJOR", "AGE"}

# 비-개인 번호 맥락 — 운송장/주문/팩스 등은 전화 형식이어도 개인정보가 아니다.
_NONPERSONAL_NUM_CTX = re.compile(
    r"운송장|송장|주문\s*번호|택배|등기|배송\s*번호|상품\s*코드|일련\s*번호|"
    r"팩스|대표\s*(?:번호|전화)|고객\s*센터")


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
        # 운송장/주문/팩스 등 비-개인 번호 맥락의 '전화'는 제외.
        if d.label == "PHONE" and _NONPERSONAL_NUM_CTX.search(text[max(0, d.start - 12):d.start]):
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
    # 자리/구분자 우회('9 0 0 1…', '900101,1234567', '900101_1234567') 회복 — 공백·콤마·
    # 세미콜론·언더스코어(전각 포함)를 걷어낸 사본에서 재검사한다. checksum·형식 검증이 있어
    # 임의 숫자 나열은 통과 못 한다. 사본 기준이라 offset(redact)은 없지만 BLOCK 은 유효하다.
    collapsed = re.sub(r"[ \t,;_，；＿]+", "", text)
    if collapsed != text:
        for d in detect_all(collapsed, exclude=_EXCLUDE):
            # 전화는 자리별 공백이 정상 표기('010 1234 5678')와 구분되지 않아 사본 회복에서 제외.
            if d.label in ("EMAIL", "PHONE") or d.text in text:
                continue  # 이메일/전화 오탐·원본에 그대로 있는 건 제외(중복 방지)
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
