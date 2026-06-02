"""형식 보존 가명화 (Format-Preserving Pseudonymization).

원본 PII 와 *같은 구조* (자릿수·구분자 위치·하이픈) 를 유지하면서 값만 바꾼다.
데이터 분석·통계 호환성이 필요할 때 사용 (예: RRN 컬럼 길이·체크섬 형태 유지).

- 결정적: 같은 입력 + 같은 vault salt → 같은 출력
- 가역적이지는 않음 (rainbow table 공격 회피). 복원이 필요하면 ``tokenize`` 사용.

알고리즘:
1. ``(label, original)`` 의 salted SHA-256 fingerprint 를 얻는다.
2. fingerprint 를 카테고리별 길이·형식에 맞춰 변환:
   - 숫자 자릿: hex → digit (mod 10)
   - 알파벳: A-Z 범위 매핑
   - 구분자(하이픈/공백/점/@)는 원위치 유지
3. RRN/카드처럼 체크섬이 있는 경우 마지막 자리는 체크섬 재계산.

본 모듈은 *진정한 FPE* (FF1/FF3) 가 아니라 **형식 보존 결정적 매핑** — 길이와
구조만 보존. 강한 암호학적 가역성이 필요하면 별도 FF1 구현 필요.

Legal basis: 「가명정보 처리 가이드라인」 (개인정보보호위원회) — 형식 보존
가명화는 데이터 효용 보존을 위한 권장 기법.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult
from ko_pii.modes._apply import apply_substitutions
from ko_pii.vault.reversible import ReversibleVault


def _digits_from_hash(fp: str, n: int) -> str:
    """Convert hex fingerprint into ``n`` decimal digits."""
    # Use the integer value of the hash and mod each digit out
    val = int(fp, 16)
    out = []
    for _ in range(n):
        out.append(str(val % 10))
        val //= 10
        if val == 0:
            val = int(fp, 16)  # cycle
    return "".join(out)


def _alpha_from_hash(fp: str, n: int) -> str:
    val = int(fp, 16)
    out = []
    for _ in range(n):
        out.append(chr(ord("A") + (val % 26)))
        val //= 26
        if val == 0:
            val = int(fp, 16)
    return "".join(out)


def _hangul_from_hash(fp: str, n: int) -> str:
    """Convert hex fingerprint into ``n`` Hangul syllables (U+AC00..U+D7A3)."""
    val = int(fp, 16)
    count = 0xD7A3 - 0xAC00 + 1  # 11172
    out = []
    for _ in range(n):
        out.append(chr(0xAC00 + (val % count)))
        val //= count
        if val == 0:
            val = int(fp, 16)
    return "".join(out)


def _fpe_rrn(original: str, fp: str) -> str:
    """RRN: 13자리, 6-7 사이 하이픈, 7번째 자리(gender) 유지."""
    digits = re.sub(r"\D", "", original)
    if len(digits) != 13:
        return _digits_from_hash(fp, len(digits))
    # RRN = 6 (date) + 1 (gender) + 5 (region) + 1 (check) = 13
    front_new = _digits_from_hash(fp[:16], 6)
    gender = digits[6]                    # gender 자리 유지 (성별 분포 보존)
    back_partial = _digits_from_hash(fp[16:30], 5)
    # 체크섬 재계산 — 첫 12자리에서 산출
    new_first_12 = front_new + gender + back_partial
    from ko_pii.checksum.rrn_checksum import compute_check_digit
    try:
        check = compute_check_digit(new_first_12)
    except ValueError:
        check = 0
    new_full = new_first_12 + str(check)
    has_hyphen = "-" in original
    return f"{new_full[:6]}-{new_full[6:]}" if has_hyphen else new_full


def _fpe_phone(original: str, fp: str) -> str:
    """전화: 자릿수·구분자·prefix 유지. 010/02/031 등은 보존."""
    digits = re.sub(r"\D", "", original)
    if len(digits) < 9:
        return _digits_from_hash(fp, len(digits))
    # 통신사·지역 prefix 보존 (식별과 무관한 *통계* 정보)
    if digits.startswith(("010", "011", "016", "017", "018", "019",
                          "070", "02")):
        prefix_len = 2 if digits.startswith("02") else 3
    elif digits.startswith(("031", "032", "033", "041", "042", "043", "044",
                            "051", "052", "053", "054", "055",
                            "061", "062", "063", "064")):
        prefix_len = 3
    else:
        prefix_len = 2
    prefix = digits[:prefix_len]
    new_tail = _digits_from_hash(fp, len(digits) - prefix_len)
    new_digits = prefix + new_tail
    # 구분자 위치 보존
    result_chars = []
    di = 0
    for ch in original:
        if ch.isdigit():
            result_chars.append(new_digits[di])
            di += 1
        else:
            result_chars.append(ch)
    return "".join(result_chars)


def _fpe_card(original: str, fp: str) -> str:
    """카드: BIN(첫 6자리) 보존 + 마지막 자리 Luhn 재계산."""
    digits = re.sub(r"\D", "", original)
    if len(digits) < 13:
        return _digits_from_hash(fp, len(digits))
    bin_part = digits[:6]
    body = _digits_from_hash(fp, len(digits) - 6 - 1)
    # Luhn 체크 디지트 계산
    from ko_pii.checksum.luhn import compute_check_digit as luhn_check_digit
    partial = bin_part + body
    try:
        check = luhn_check_digit(partial)
    except Exception:
        check = 0
    new_digits = partial + str(check)
    result_chars = []
    di = 0
    for ch in original:
        if ch.isdigit():
            result_chars.append(new_digits[di])
            di += 1
        else:
            result_chars.append(ch)
    return "".join(result_chars)


def _fpe_email(original: str, fp: str) -> str:
    """이메일: 도메인은 그대로, 로컬 부분만 무작위 영숫자."""
    if "@" not in original:
        return original
    local, _, domain = original.partition("@")
    new_local = _alpha_from_hash(fp, max(4, len(local))).lower()[:len(local)]
    return f"{new_local}@{domain}"


def _fpe_passport(original: str, fp: str) -> str:
    """여권: prefix(M/S/PP 등) 유지, 8자리 숫자만 변경."""
    m = re.match(r"^([A-Z]{1,2})(\d+)$", original)
    if not m:
        return original
    prefix, digits = m.group(1), m.group(2)
    return prefix + _digits_from_hash(fp, len(digits))


def _fpe_default(original: str, fp: str) -> str:
    """기본: 길이·문자 종류(숫자/영문/한글) 유지."""
    chars = []
    digit_pool = _digits_from_hash(fp, len(original))
    alpha_pool = _alpha_from_hash(fp, len(original))
    hangul_pool = _hangul_from_hash(fp, len(original))
    di = ai = hi = 0
    for ch in original:
        if ch.isdigit():
            chars.append(digit_pool[di]); di += 1
        elif "가" <= ch <= "힣":  # 한글 음절 → 한글로 치환 (형식 유지; isalpha 가 한글도 True 라 먼저 처리)
            chars.append(hangul_pool[hi]); hi += 1
        elif ch.isascii() and ch.isalpha():
            chars.append(alpha_pool[ai] if ch.isupper() else alpha_pool[ai].lower())
            ai += 1
        else:
            chars.append(ch)  # 구분자 등은 그대로
    return "".join(chars)


_FPE_BY_LABEL = {
    "RRN": _fpe_rrn,
    "FRN": _fpe_rrn,
    "PHONE": _fpe_phone,
    "FAX": _fpe_phone,
    "CARD": _fpe_card,
    "EMAIL": _fpe_email,
    "PASSPORT": _fpe_passport,
}


def fpe(
    text: str,
    detections: Iterable[DetectionResult],
    vault: Optional[ReversibleVault] = None,
) -> tuple[str, ReversibleVault]:
    """Replace each detection with a format-preserving pseudo-value.

    Returns ``(replaced_text, vault)``. The vault stores the original-to-fake
    mapping so reproducible regeneration is possible (not strictly reversible).
    """
    v = vault if vault is not None else ReversibleVault()
    detections = list(detections)

    def replace(d: DetectionResult) -> str:
        fp = v.fingerprint(d.label, d.text)
        fn = _FPE_BY_LABEL.get(d.label, _fpe_default)
        new_value = fn(d.text, fp)
        # Store the mapping for audit
        v.store(
            label=d.label,
            original=d.text,
            risk_level=int(d.risk_level),
            legal_basis=d.legal_basis,
            offset=d.start,
            extra={**dict(d.extra), "fpe_value": new_value},
        )
        return new_value

    replaced = apply_substitutions(text, detections, replace)
    return replaced, v
