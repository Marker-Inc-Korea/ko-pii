"""Email address detection (simplified RFC 5322).

The full RFC 5322 grammar is complex and includes constructs (quoted local
parts, IP-address domain literals, comments) that essentially never appear in
Korean public-sector documents. This module uses a pragmatic subset.

Legal basis: 개인정보보호법 제2조.
"""
from __future__ import annotations

import re
import string
from typing import Iterator

from ko_pii.core.overlap import _select_non_overlapping
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "EMAIL"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+)"
    r"(?![A-Za-z0-9])"
)

# Korean IDN labels with an ASCII final label. Unicode local parts and Unicode
# TLDs are outside this subset: particles make their boundaries ambiguous.
_IDN_LABEL = r"[A-Za-z0-9가-힣](?:[A-Za-z0-9가-힣\-]*[A-Za-z0-9가-힣])?"
_IDN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-가-힣])([A-Za-z0-9._%+\-]+@"
    + _IDN_LABEL + r"(?:\." + _IDN_LABEL + r")*\.[A-Za-z]{2,63})(?![A-Za-z0-9\-])"
)


def _split_literal_email(value: str) -> tuple[str, str] | None:
    """Return parts only for one complete address in our supported subset.

    Field assertions may contain lists or prose. Transformers must not retain
    everything after the first @ as if it were a single harmless domain.
    """
    if _PATTERN.fullmatch(value) is None and _IDN_PATTERN.fullmatch(value) is None:
        return None
    local, _, domain = value.partition("@")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return None
    try:
        ascii_domain = domain.encode("idna")
    except UnicodeError:
        return None
    if len(ascii_domain) > 253:
        return None
    return local, domain

# 난독화 이메일(GAP 3): '[at]'/'(at)' · '[dot]'/'(dot)' 치환과 '@'/'.' 주변 공백 주입으로
# 마스킹을 회피하는 우회.
#   - "hong [at] gmail [dot] com"      → hong@gmail.com
#   - "hong gildong @ naver . com"     → 로컬 내부 공백은 명시적 opt-in
# recall-safe 설계:
#   - @ 등가물은 실제 '@' 또는 대괄호/소괄호로 감싼 at 만 허용(맨단어 ' at '는 산문 FP
#     위험이 커 제외 — "meet at noon" 등).
#   - dot 등가물도 실제 '.' 또는 괄호 감싼 dot 만. 도메인 라벨이 1개 이상 점으로 이어질
#     때만 매치 → 'admin@host'(점 없음)·'10 . 5'(라벨 아님)는 미해당.
_OBF_AT = r"(?:@|\[[ \t]*at[ \t]*\]|\([ \t]*at[ \t]*\))"
_OBF_DOT = r"(?:\.|\[[ \t]*dot[ \t]*\]|\([ \t]*dot[ \t]*\))"
_OBF_LOCAL = r"[A-Za-z0-9._%+\-]+"
_OBF_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"


def _obfuscated_pattern(local: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z0-9._%+\-@])" + local
        + r"[ \t]*" + _OBF_AT + r"[ \t]*" + _OBF_LABEL
        + r"(?:[ \t]*" + _OBF_DOT + r"[ \t]*" + _OBF_LABEL + r")+"
        r"(?![A-Za-z0-9])", re.IGNORECASE,
    )


_OBFUSCATED = _obfuscated_pattern(_OBF_LOCAL)
_OBFUSCATED_SPACED = _obfuscated_pattern(_OBF_LOCAL + r"(?:[ \t]+" + _OBF_LOCAL + r")*")
_AT_MARKER = re.compile(_OBF_AT, re.IGNORECASE)
_DOMAIN_AFTER_AT = re.compile(
    r"[ \t]*" + _OBF_LABEL + r"(?:[ \t]*" + _OBF_DOT + r"[ \t]*" + _OBF_LABEL + r")+(?![A-Za-z0-9])",
    re.IGNORECASE,
)
# re.IGNORECASE also admits these four Unicode letters in [A-Z].
_LOCAL_CHARS = frozenset(string.ascii_letters + string.digits + "._%+-İıſK")


def _obfuscated_matches(text: str, *, allow_spaced_local: bool = False) -> Iterator[re.Match[str]]:
    """Anchor on valid at/domain pairs instead of retrying every local word."""
    cursor = 0
    for at in _AT_MARKER.finditer(text):
        if at.start() < cursor or _DOMAIN_AFTER_AT.match(text, at.end()) is None:
            continue
        start = at.start()
        while start > cursor and text[start - 1] in " \t":
            start -= 1
        # A preceding prose word is not part of the local part by default.
        allowed = _LOCAL_CHARS | {" ", "\t"} if allow_spaced_local else _LOCAL_CHARS
        while start > cursor and text[start - 1] in allowed:
            start -= 1
        while start < at.start() and text[start] in " \t":
            start += 1
        # The original lookbehind forbids starting directly after another @.
        if start > 0 and text[start - 1] in _LOCAL_CHARS | {"@"}:
            while start < at.start() and text[start] in _LOCAL_CHARS:
                start += 1
            while start < at.start() and text[start] in " \t":
                start += 1
        if start < at.start():
            pattern = _OBFUSCATED_SPACED if allow_spaced_local else _OBFUSCATED
            match = pattern.match(text, start)
            if match is not None:
                cursor = match.end()
                yield match

# 난독화 토큰([at]/[dot]/괄호/공백)을 표준형으로 환원.
_DEOBF_AT = re.compile(r"\s*(?:\[\s*at\s*\]|\(\s*at\s*\))\s*", re.IGNORECASE)
_DEOBF_DOT = re.compile(r"\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\))\s*", re.IGNORECASE)


def _canonicalize(raw: str) -> str | None:
    """난독화 이메일 원문 → 표준 'local@domain'. 비정상이면 None."""
    s = _DEOBF_AT.sub("@", raw)
    s = _DEOBF_DOT.sub(".", s)
    s = s.replace(" ", "").replace("\t", "")
    local, sep, domain = s.rpartition("@")
    if not sep or not local or not domain:
        return None
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return None
    if "." not in domain or ".." in domain or domain.startswith(".") or domain.endswith("."):
        return None
    return s


def detect(text: str, *, allow_spaced_local: bool = False) -> Iterator[DetectionResult]:
    """Detect emails without consuming preceding prose or crossing lines.

    ``allow_spaced_local=True`` joins local-part words on the same line. Use
    only for isolated email fields: it cannot distinguish those words from
    surrounding English prose. The default recognizes the nearest local word.
    """
    candidates: list[DetectionResult] = []

    for m in _PATTERN.finditer(text):
        value = m.group(1)
        local, _, domain = value.rpartition("@")
        # Reject obvious malformed cases the regex permits
        if local.startswith(".") or local.endswith("."):
            continue
        if ".." in local or ".." in domain:
            continue
        candidates.append(DetectionResult(
            label=LABEL,
            text=value,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=1.0,
            evidence=["pattern:email"],
            subrule_id="email.ascii.v1",
            legal_basis=LEGAL_BASIS,
            extra={
                "value": value,
                "local": local,
                "domain": domain,
                "category": CATEGORY,
            },
        ))

    for m in _IDN_PATTERN.finditer(text):
        value = m.group(1)
        local, _, domain = value.rpartition("@")
        if domain.isascii() or local.startswith(".") or local.endswith(".") or ".." in local:
            continue
        try:
            ascii_domain = domain.encode("idna").decode("ascii")
        except UnicodeError:
            continue
        if len(ascii_domain) > 253:
            continue
        candidates.append(DetectionResult(
            label=LABEL, text=value, start=m.start(), end=m.end(),
            risk_level=RiskLevel.MEDIUM, confidence=1.0,
            evidence=["pattern:email_idn"], legal_basis=LEGAL_BASIS,
            subrule_id="email.korean_domain.v1",
            extra={"value": value, "local": local, "domain": domain,
                   "ascii_domain": ascii_domain, "category": CATEGORY},
        ))

    # 난독화 이메일 — 표준 패턴에 안 잡힌 우회 형태. 표준 매치와 겹치면 건너뜀.
    for m in _obfuscated_matches(text, allow_spaced_local=allow_spaced_local):
        canon = _canonicalize(m.group(0))
        if canon is None:
            continue
        local, _, domain = canon.rpartition("@")
        candidates.append(DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=1.0,
            evidence=["pattern:email", "obfuscated:deobfuscated"],
            subrule_id="email.obfuscated.v1",
            legal_basis=LEGAL_BASIS,
            extra={
                "value": canon,
                "local": local,
                "domain": domain,
                "category": CATEGORY,
                "obfuscated": True,
            },
        ))
    yield from _select_non_overlapping(candidates)
