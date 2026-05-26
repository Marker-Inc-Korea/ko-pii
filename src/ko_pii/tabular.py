"""표 / 컬럼 단위 가명화 — CSV·XLSX·DB record 처리.

평문 텍스트로 변환하지 않고 *컬럼 단위* 로 처리:
- 헤더 명을 PII 카테고리에 자동 매핑 (성명 → PERSON, 주민번호 → RRN, ...)
- 각 셀에 대해 *해당 카테고리만* 검출 (다른 검출기 비활성 → 정확도 ↑)
- 가명화 후 *같은 표 구조* 유지

지원:
- ``anonymize_records(records, ...)`` — list[dict] → list[dict]
- ``map_columns(headers)`` — 헤더 → 라벨 매핑 자동 추론

법적 근거: 개인정보보호법 제28조의2~5 (가명정보 처리 특례). 구조 보존이
분석 호환성에 직결.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from ko_pii.anonymizer import Anonymizer
from ko_pii.core.modes import ProcessingMode
from ko_pii.core.types import DetectionResult
from ko_pii.vault.reversible import ReversibleVault


# 헤더 → PII 라벨 매핑 (한국 공문서·민원·인사 도메인 빈출 표현)
_HEADER_MAP: dict[str, str] = {
    # 성명
    "성명": "PERSON", "이름": "PERSON", "성함": "PERSON", "성  명": "PERSON",
    "신청인": "PERSON", "민원인": "PERSON", "기안자": "PERSON", "수신자": "PERSON",
    "당사자": "PERSON", "환자명": "PERSON", "환자": "PERSON",
    "name": "PERSON", "Name": "PERSON", "NAME": "PERSON",
    "성명(한글)": "PERSON",

    # RRN
    "주민번호": "RRN", "주민등록번호": "RRN", "주민": "RRN",
    "주민등록번호 13자리": "RRN",
    "rrn": "RRN", "RRN": "RRN",

    # 외국인등록번호
    "외국인등록번호": "FRN", "외등번호": "FRN",

    # 사업자번호
    "사업자등록번호": "BUSINESS_REG", "사업자번호": "BUSINESS_REG",
    "biz_reg": "BUSINESS_REG",

    # 법인번호
    "법인등록번호": "CORP_REG", "법인번호": "CORP_REG",

    # 운전면허
    "운전면허번호": "DRIVER_LICENSE", "면허번호": "DRIVER_LICENSE",

    # 여권
    "여권번호": "PASSPORT", "여권": "PASSPORT",

    # 카드
    "카드번호": "CARD", "신용카드번호": "CARD", "체크카드번호": "CARD",

    # 의료보험
    "건강보험증번호": "MEDICAL_INSURANCE", "건강보험번호": "MEDICAL_INSURANCE",

    # 처방
    "처방번호": "PRESCRIPTION_ID", "처방전번호": "PRESCRIPTION_ID",

    # 전화
    "전화번호": "PHONE", "연락처": "PHONE", "휴대전화": "PHONE",
    "휴대폰": "PHONE", "휴대폰번호": "PHONE", "핸드폰": "PHONE",
    "이동전화": "PHONE", "휴대전화번호": "PHONE",
    "phone": "PHONE", "tel": "PHONE", "Tel": "PHONE", "TEL": "PHONE",
    "Phone": "PHONE",

    # 팩스
    "팩스": "FAX", "팩스번호": "FAX",

    # 이메일
    "이메일": "EMAIL", "전자우편": "EMAIL", "메일": "EMAIL",
    "email": "EMAIL", "Email": "EMAIL", "E-mail": "EMAIL", "EMAIL": "EMAIL",

    # 주소
    "주소": "ADDRESS", "거주지": "ADDRESS", "거주지 주소": "ADDRESS",
    "도로명주소": "ADDRESS", "지번주소": "ADDRESS",
    "address": "ADDRESS", "Address": "ADDRESS",

    # 우편번호
    "우편번호": "POSTAL_CODE", "우편": "POSTAL_CODE",
    "zip": "POSTAL_CODE", "zipcode": "POSTAL_CODE", "Zip": "POSTAL_CODE",

    # 차량
    "차량번호": "VEHICLE", "자동차번호": "VEHICLE", "차량": "VEHICLE",

    # 계좌
    "계좌번호": "ACCOUNT", "계좌": "ACCOUNT", "통장번호": "ACCOUNT",
    "은행계좌": "ACCOUNT",

    # 사번
    "사번": "EMPLOYEE_ID", "공무원번호": "EMPLOYEE_ID", "직원번호": "EMPLOYEE_ID",
    "교번": "EMPLOYEE_ID",

    # IP
    "IP": "IP", "ip": "IP", "IP주소": "IP", "ip_address": "IP",

    # URL
    "URL": "URL", "url": "URL", "홈페이지": "URL", "웹사이트": "URL",

    # 토지
    "PNU": "PNU", "필지고유번호": "PNU", "토지고유번호": "PNU",

    # 약품
    "약품코드": "EDI_DRUG", "의약품코드": "EDI_DRUG",

    # 사건번호
    "사건번호": "COURT_CASE",
}


def _normalize_header(h: str) -> str:
    """공백·괄호 등 정규화."""
    return re.sub(r"\s+", "", h).strip()


def map_columns(headers: Iterable[str]) -> dict[str, str]:
    """각 헤더에 대해 추정 PII 라벨 반환 (없으면 키 부재).

    >>> map_columns(["성명", "주민번호", "메모"])
    {'성명': 'PERSON', '주민번호': 'RRN'}
    """
    mapping: dict[str, str] = {}
    for h in headers:
        norm = _normalize_header(h)
        if h in _HEADER_MAP:
            mapping[h] = _HEADER_MAP[h]
        elif norm in _HEADER_MAP:
            mapping[h] = _HEADER_MAP[norm]
        else:
            # 부분 매칭 — "신청인 성명" 같은 합성 헤더
            for key, lbl in _HEADER_MAP.items():
                if len(key) >= 2 and key in h:
                    mapping[h] = lbl
                    break
    return mapping


def _force_anonymize_cell(value: str, label: str, strategy: str,
                           vault: ReversibleVault) -> str:
    """컬럼이 명시적 라벨일 때 — 검출기 점수 우회하고 cell 전체를 가명화."""
    from ko_pii.core.types import RiskLevel
    from ko_pii.legal.mapping import risk_floor_for, legal_basis_for

    risk = risk_floor_for(label) or RiskLevel.MEDIUM
    if strategy == "tokenize":
        return vault.store(label, value, int(risk), legal_basis=legal_basis_for(label))
    if strategy == "redact":
        from ko_pii.modes.redact import label_to_hangul
        return f"[{label_to_hangul(label)}]"
    if strategy == "asterisk":
        return "*" * len(value)
    if strategy == "partial":
        from ko_pii.modes.partial import mask_value
        return mask_value(label, value)
    if strategy == "hashed":
        fp = vault.fingerprint(label, value)
        return f"<{label}:{fp[:12]}>"
    if strategy == "fpe":
        from ko_pii.modes.fpe import _FPE_BY_LABEL, _fpe_default
        fp = vault.fingerprint(label, value)
        fn = _FPE_BY_LABEL.get(label, _fpe_default)
        new_val = fn(value, fp)
        vault.store(label, value, int(risk), legal_basis=legal_basis_for(label),
                    extra={"fpe_value": new_val})
        return new_val
    return value


def anonymize_records(
    records: list[dict[str, str]],
    *,
    column_map: Optional[dict[str, str]] = None,
    mode: ProcessingMode = ProcessingMode.STRICT,
    strategy: str = "tokenize",
    vault: Optional[ReversibleVault] = None,
) -> tuple[list[dict[str, str]], ReversibleVault]:
    """레코드(표) 단위 가명화 — 같은 구조 유지.

    Parameters
    ----------
    records : list of dict
        ``read_records`` 등에서 얻은 행 데이터.
    column_map : optional dict
        ``{header: label}`` 매핑 명시. 미지정 시 ``map_columns`` 로 자동 추론.
    mode, strategy, vault :
        :class:`Anonymizer` 와 동일.

    Returns
    -------
    (anonymized_records, vault) :
        같은 dict 구조의 가명화 결과 + 공유된 vault.
        매핑된 컬럼 *외* 의 값들은 원본 그대로 보존.
    """
    if not records:
        return [], (vault or ReversibleVault())

    if column_map is None:
        column_map = map_columns(records[0].keys())

    if vault is None:
        vault = ReversibleVault()

    out: list[dict[str, str]] = []
    for rec in records:
        new_rec: dict[str, str] = {}
        for header, value in rec.items():
            label = column_map.get(header)
            if not label or not value:
                new_rec[header] = value
                continue
            # 컬럼 매핑 = 명시적 라벨 단언 → 검출기 임계값 우회
            new_rec[header] = _force_anonymize_cell(value, label, strategy, vault)
        out.append(new_rec)

    return out, vault
