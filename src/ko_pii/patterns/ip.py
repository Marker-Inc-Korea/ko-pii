"""IP address detection (IPv4 + IPv6).

IPv4: 4 octets in 0–255 with no more than 3 digits each.

IPv6: RFC 4291 형식 — 1~8 grouping of hex tetrets separated by colons;
"::" 단축 표기 1회 허용; IPv4 매핑 (예: ``::ffff:192.0.2.1``) 도 인정.

Legal basis: 개인정보보호법 제2조 — IP 주소는 결합 시 개인을 식별할 수 있는
정보로 보아 보호 대상이 될 수 있음 (방통위/개인정보위 해석).
"""
from __future__ import annotations

import ipaddress
import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "IP"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

_IPV4 = re.compile(
    r"(?<![0-9.])"
    r"((?:[0-9]{1,3}\.){3}[0-9]{1,3})"
    r"(?![0-9.])"
)

# IPv6 candidate: any run of hex digits, colons, and an optional embedded
# IPv4 tail (for ``::ffff:1.2.3.4``). Final validity is decided by the
# standard library so we keep the regex deliberately permissive.
_IPV6 = re.compile(
    r"(?<![0-9A-Fa-f:.])"
    r"("
    r"[0-9A-Fa-f:]*::[0-9A-Fa-f:]*(?:\d{1,3}(?:\.\d{1,3}){3})?"
    r"|"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r")"
    r"(?:%[A-Za-z0-9]+)?"
    r"(?![0-9A-Fa-f:.])"
)


def _is_valid_ipv4(addr: str) -> bool:
    parts = addr.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not (1 <= len(p) <= 3):
            return False
        if not (0 <= int(p) <= 255):
            return False
    return True


def _is_reserved_ipv4(addr: str) -> bool:
    """IANA 특수목적 주소 — 개인 식별과 무관해 PII 가 아니다(loopback 127.0.0.1 등).
    사설망(10/172.16/192.168)은 결합 시 식별 가능성이 있어 제외하지 않는다(recall 보존)."""
    a, b, c, _d = (int(x) for x in addr.split("."))
    return (
        a == 127                       # loopback 127/8
        or a == 0                      # "this network" 0/8
        or (a == 169 and b == 254)     # link-local 169.254/16
        or (a == 192 and b == 0 and c == 2)      # TEST-NET-1 (문서용)
        or (a == 198 and b == 51 and c == 100)   # TEST-NET-2
        or (a == 203 and b == 0 and c == 113)    # TEST-NET-3
        or a >= 224                    # multicast / reserved 224.0.0.0+
    )


def _is_valid_ipv6(addr: str) -> bool:
    # Strip zone id (e.g. "fe80::1%eth0") — ipaddress doesn't accept it
    raw = addr.split("%", 1)[0]
    try:
        ipaddress.IPv6Address(raw)
        return True
    except ValueError:
        return False


# 버전/빌드 문자열은 IPv4 와 형식이 같다('소프트웨어 버전 10.0.19.41'). 좌측에 버전
# 단서가 바로 붙거나(예 'v10.0.19.41') 근접하면 IP 로 채택하지 않는다(과탐 방지).
# 영문 토큰은 단어 경계로 한정 — 'server'/'driver' 내부의 'ver' 오매칭 방지.
_VERSION_CTX = re.compile(
    r"(?:버전|버젼|펌웨어|릴리[스즈]|빌드|패치|"
    r"(?<![A-Za-z])(?:[vV]\.?|ver\.?|version|firmware|release|build|patch))\s*$"
)
# 문서 섹션/항목 번호('표 3.2.1.4', 'Section 4.2.1.3')도 IPv4 형식이라 좌측 단서로 제외.
_SECTION_CTX = re.compile(
    r"(?:"
    r"표|그림|별표|도표|붙임|항목|조항|조|항|단계|절|장|버전|챕터"
    r"|[Ss]ection|[Cc]hapter|[Ff]igure|[Tt]able|[Aa]ppendix|[Cc]lause"
    r"|(?<![A-Za-z])(?:[Ss]ec|[Cc]h|[Ff]ig|[Aa]pp)\.?"
    r")\s*$"
)
# 우측에 '버전' 단서가 바로 붙는 경우('2.10.4.5 버전입니다')도 버전 문자열로 본다.
_VERSION_RIGHT = re.compile(r"^\s*(?:버전|버젼|version|빌드|build|릴리[스즈])")


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    for m in _IPV4.finditer(text):
        addr = m.group(1)
        if not _is_valid_ipv4(addr) or _is_reserved_ipv4(addr):
            continue
        left = text[max(0, m.start() - 12):m.start()]
        if _VERSION_CTX.search(left) or _SECTION_CTX.search(left):
            continue
        if _VERSION_RIGHT.search(text[m.end():m.end() + 8]):
            continue
        span = (m.start(), m.end())
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=addr,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=1.0,
            evidence=["pattern:ipv4"],
            legal_basis=LEGAL_BASIS,
            extra={"version": 4, "value": addr, "category": CATEGORY},
        )

    for m in _IPV6.finditer(text):
        span = (m.start(), m.end())
        if span in seen:
            continue
        addr = m.group(0)
        # Filter trivial cases that the loose regex may match.
        if ":" not in addr:
            continue
        # 단독 "::" 만 매칭은 거부 — 텍스트에서 *주 내용 ::* 같은 패턴
        # (한국어 자유 텍스트의 ":" 강조 표기)
        if addr.strip() in ("::", ""):
            continue
        if not _is_valid_ipv6(addr):
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=addr,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=1.0,
            evidence=["pattern:ipv6"],
            legal_basis=LEGAL_BASIS,
            extra={"version": 6, "value": addr, "category": CATEGORY},
        )
