"""부분 마스킹 (Partial Redaction) — 공문서 표준 양식 호환.

실제 한국 공문서는 PII 의 일부만 마스킹하는 경우가 많다:
  - 성명:    "홍길동" → "홍OO" (성만 노출)
  - 주민번호: "880101-1234568" → "880101-1******" (앞 6자리만 노출)
  - 전화:    "010-1234-5678" → "010-****-5678" (양 끝만 노출)
  - 이메일:  "user@example.com" → "u***@example.com"
  - 카드:    "1234-5678-9012-3456" → "1234-****-****-3456"
  - 주소:    "서울특별시 강남구 ..." → "서울특별시 강남구 ***"

각 카테고리별 표준 마스킹 룰을 ``partial`` 함수에 제공한다.

Legal basis: 「개인정보 비식별 조치 가이드라인」 (개인정보보호위원회) —
"부분 마스킹은 비식별 조치의 *부분 일반화* 형태로 인정".
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

from ko_pii.core.types import DetectionResult
from ko_pii.modes._apply import apply_substitutions

MASK = "*"


def _mask_rrn(text: str) -> str:
    """``880101-1234568`` → ``880101-1******`` (생년 + gender 만 노출)."""
    digits = re.sub(r"\D", "", text)
    if len(digits) != 13:
        return MASK * len(text)
    has_hyphen = "-" in text
    front = digits[:6]
    gender = digits[6]
    masked_back = MASK * 6
    return f"{front}-{gender}{masked_back}" if has_hyphen else f"{front}{gender}{masked_back}"


def _mask_phone(text: str) -> str:
    """전화번호 마스킹 — 한국 번호 체계 보존.

    Examples:
        010-1234-5678   → 010-****-5678
        02-1234-5678    → 02-****-5678  (서울은 2자리 지역번호)
        02-123-4567     → 02-***-4567
        031-987-6543    → 031-***-6543
        +82-10-1234-5678 → +82-10-****-5678
        +82-2-1234-5678  → +82-2-****-5678
        1588-1234       → 1588-****
        0504-1234-5678  → 0504-****-5678 (안심번호)
    """
    digits = re.sub(r"\D", "", text)
    if len(digits) < 7:
        return MASK * len(text)
    has_plus = text.startswith("+")
    if "-" in text:
        sep = "-"
    elif "." in text:
        sep = "."
    elif " " in text:
        sep = " "
    else:
        sep = ""

    # +82 국가 코드
    if has_plus and digits.startswith("82"):
        rest = digits[2:]
        if rest.startswith("2"):
            # 서울: +82-2-XXXX-XXXX (앞자리 2 = 02 의 leading 0 제거)
            sub = rest[1:]
            mid = MASK * max(3, len(sub) - 4)
            return f"+82{sep}2{sep}{mid}{sep}{sub[-4:]}"
        if len(rest) >= 9:
            # 모바일 (10/11/16-19) 및 3자리 지역번호 (31~64, 70)
            area = rest[:2]
            sub = rest[2:]
            mid = MASK * max(3, len(sub) - 4)
            return f"+82{sep}{area}{sep}{mid}{sep}{sub[-4:]}"

    # 050X 안심번호 (12자리: 050X + 4 + 4)
    if digits.startswith("050") and len(digits) == 12:
        return f"{digits[:4]}{sep}{MASK*4}{sep}{digits[-4:]}"

    # 서울 02 (2자리 지역번호)
    if digits.startswith("02") and len(digits) in (9, 10):
        sub_len = len(digits) - 2
        return f"02{sep}{MASK*(sub_len-4)}{sep}{digits[-4:]}"

    # 1588/1577/1644 형식 (8자리, 지역번호 없음)
    if len(digits) == 8 and digits[:2] in {"15", "16", "18"}:
        return f"{digits[:4]}{sep}{MASK*4}"

    # 모바일 (010-019) 및 3자리 지역번호 (031-064, 070)
    if len(digits) >= 11:
        return f"{digits[:3]}{sep}{MASK*4}{sep}{digits[-4:]}"
    if len(digits) == 10:
        return f"{digits[:3]}{sep}{MASK*3}{sep}{digits[-4:]}"
    if len(digits) == 9:
        return f"{digits[:2]}{sep}{MASK*3}{sep}{digits[-4:]}"
    return MASK * len(text)


def _mask_email(text: str) -> str:
    """``user@example.com`` → ``u***@example.com`` (로컬 앞자만 노출)."""
    if "@" not in text:
        return MASK * len(text)
    local, _, domain = text.partition("@")
    if not local:
        return text
    if len(local) <= 1:
        return f"{local}{MASK*3}@{domain}"
    return f"{local[0]}{MASK*max(3, len(local)-1)}@{domain}"


def _mask_card(text: str) -> str:
    """``1234-5678-9012-3456`` → ``1234-****-****-3456`` (BIN + 마지막 4)."""
    digits = re.sub(r"\D", "", text)
    if len(digits) < 8:
        return MASK * len(text)
    # 길이 보존하면서 중간만 가림
    has_hyphen = "-" in text
    has_space = " " in text
    sep = "-" if has_hyphen else (" " if has_space else "")
    front = digits[:4]
    back = digits[-4:]
    middle_len = len(digits) - 8
    if sep:
        # 4자리 그룹 형태로 재조합
        groups = [front]
        i = 4
        while i < len(digits) - 4:
            groups.append(MASK * min(4, len(digits) - 4 - i))
            i += 4
        groups.append(back)
        return sep.join(groups)
    return f"{front}{MASK*middle_len}{back}"


def _mask_name(text: str) -> str:
    """``홍길동`` → ``홍OO`` (성만 노출, 이름은 한국 표준 O 로 마스킹)."""
    from ko_pii.dictionaries.surnames import surname_prefix_len
    sp = surname_prefix_len(text)
    if sp == 0:
        sp = 1  # 폴백: 첫 글자만 노출
    if len(text) <= sp:
        return text
    return text[:sp] + ("O" * (len(text) - sp))


def _mask_address(text: str) -> str:
    """주소: 시·도/시·군·구까지만 노출, 도로명 이하 마스킹."""
    from ko_pii.generalization.address import generalize_address
    g = generalize_address(text, level="district")
    return g + " " + MASK * 3 if g != text else MASK * len(text)


def _mask_account(text: str) -> str:
    """계좌: 앞 4 + 끝 4 노출, 중간 마스킹."""
    digits = re.sub(r"\D", "", text)
    if len(digits) < 8:
        return MASK * len(text)
    return f"{digits[:4]}{MASK*(len(digits)-8)}{digits[-4:]}"


def _mask_passport(text: str) -> str:
    """여권: prefix + 마지막 2자리 노출."""
    m = re.match(r"^([A-Z]{1,2})(\d+)$", text)
    if not m:
        return MASK * len(text)
    prefix, digits = m.group(1), m.group(2)
    return f"{prefix}{MASK*(len(digits)-2)}{digits[-2:]}"


def _mask_default(text: str) -> str:
    """기본: 전체 마스킹 (가능하면 양 끝 2자리는 노출)."""
    if len(text) <= 4:
        return MASK * len(text)
    return text[:2] + MASK * (len(text) - 4) + text[-2:]


def _mask_birth(text: str) -> str:
    """생년월일: 연도만 노출, 월/일 마스킹.

    1988년 1월 1일 → 1988년 **월 *일
    1988-01-01     → 1988-**-**
    88.01.01       → 88.**.**
    88년생          → 그대로 (이미 연도만)
    """
    # "년생" 형태는 이미 연도만 → 그대로 두거나 마스킹 강도 낮음
    if text.endswith("년생"):
        return text
    # 한국어: 1988년 X월 X일
    m = re.match(r"^(\d{2,4})\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일$", text)
    if m:
        return f"{m.group(1)}년 {MASK*2}월 {MASK*2}일"
    # 숫자 형식: 1988.01.01 / 1988-01-01 / 1988/01/01 / 88.01.01
    m = re.match(r"^(\d{2,4})([./-])\d{1,2}\2\d{1,2}$", text)
    if m:
        sep = m.group(2)
        return f"{m.group(1)}{sep}{MASK*2}{sep}{MASK*2}"
    return MASK * len(text)


def _mask_education(text: str) -> str:
    """학력: 대학교명 → 'X대학교' (계열은 보존하지 않고 한글 X 로 치환).

    서울대학교 → ○대학교
    KAIST     → ○○○○○ (영문은 모두 가림)
    """
    # 한국어 대학교명: 첫 글자만 ○ 로 + "대학교/대학" 유지
    for suf in ("대학원대학교", "전문대학", "대학교", "대학"):
        if text.endswith(suf):
            return "○" + suf
    # 영문 약칭 (KAIST 등) → 전체 마스킹
    return MASK * len(text)


def _mask_major(text: str) -> str:
    """전공: 계열까지만 노출.

    컴퓨터공학과 → ○○○○학과
    경영학       → ○○학
    """
    # 접미사 유지
    for suf in ("학과", "학부", "전공", "학", "과"):
        if text.endswith(suf) and len(text) > len(suf):
            stem = text[: -len(suf)]
            return ("○" * len(stem)) + suf
    return MASK * len(text)


def _mask_position(text: str) -> str:
    """직책: 그대로 (이미 일반화된 직급)."""
    return text


def _mask_age(text: str) -> str:
    """나이: 10세 단위 구간화. '32세' → '30대'."""
    m = re.search(r"(\d+)", text)
    if m:
        age = int(m.group(1))
        if age < 10:
            return "10대 미만"
        decade = (age // 10) * 10
        return f"{decade}대"
    return MASK * len(text)


def _mask_height(text: str) -> str:
    """신장: 5cm 구간화. '175cm' → '175~180cm'."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        h = float(m.group(1))
        # m 단위면 cm 로 변환
        if h < 3:
            h *= 100
        lo = int(h // 5) * 5
        return f"{lo}-{lo+5}cm"
    return MASK * len(text)


def _mask_weight(text: str) -> str:
    """체중: 5kg 구간화. '70kg' → '70~75kg'."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        w = float(m.group(1))
        lo = int(w // 5) * 5
        return f"{lo}-{lo+5}kg"
    return MASK * len(text)


_MASKERS: dict[str, Callable[[str], str]] = {
    "RRN": _mask_rrn,
    "FRN": _mask_rrn,
    "PHONE": _mask_phone,
    "FAX": _mask_phone,
    "EMAIL": _mask_email,
    "CARD": _mask_card,
    "PERSON": _mask_name,
    "ADDRESS": _mask_address,
    "ACCOUNT": _mask_account,
    "PASSPORT": _mask_passport,
    # KDPII 표준 준식별자
    "DT_BIRTH": _mask_birth,
    "EDUCATION": _mask_education,
    "MAJOR": _mask_major,
    "POSITION": _mask_position,
    "AGE": _mask_age,
    "HEIGHT": _mask_height,
    "WEIGHT": _mask_weight,
}


def partial(
    text: str,
    detections: Iterable[DetectionResult],
) -> str:
    """Apply category-aware partial masking to each detection span."""

    def replace(d: DetectionResult) -> str:
        masker = _MASKERS.get(d.label, _mask_default)
        return masker(d.text)

    return apply_substitutions(text, detections, replace)


def mask_value(label: str, value: str) -> str:
    """Stand-alone helper: ``mask_value("RRN", "880101-1234568")`` → ``880101-1******``."""
    masker = _MASKERS.get(label, _mask_default)
    return masker(value)
