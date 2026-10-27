"""표 / 컬럼 단위 가명화 — CSV·XLSX·DB record 처리.

평문 텍스트로 변환하지 않고 *컬럼 단위* 로 처리:
- 헤더 명을 PII 카테고리에 자동 매핑 (성명 → PERSON, 주민번호 → RRN, ...)
- 매핑된 열의 셀 전체를 해당 카테고리로 단언하여 변환
- 가명화 후 *같은 표 구조* 유지

지원:
- ``anonymize_records(records, ...)`` — list[dict] → list[dict]
- ``map_columns(headers)`` — 헤더 → 라벨 매핑 자동 추론

열 매핑은 호출자 스키마의 단언이며 실제 개인정보 여부나 법적 익명성 판정이 아니다.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
from typing import Any, Iterable, Literal, Optional

from ko_pii.anonymizer import Anonymizer
from ko_pii.core.modes import ProcessingMode
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


_SCHEMA_AMBIGUOUS_HEADERS = frozenset({
    "name",
    "address",
    "url",
    "ip",
    "이름",
    "환자",
    "주민",
    "카드",
    "메일",
    "우편",
    "차량",
    "계좌",
})


@dataclass(frozen=True)
class SchemaColumnClassification:
    """Evidence for an exact schema-column classification.

    ``map_columns`` also supports a limited set of qualified field names.
    SQL policy compilation must be stricter:
    a column such as ``product_name`` must never inherit the ``name`` mapping.
    This record therefore describes exact or whitespace/case-normalized matches
    only, and marks generic aliases with lower confidence for explicit review.
    """

    column: str
    label: str
    confidence: float
    match: Literal["exact", "normalized"]
    matched_header: str
    ambiguous: bool


def _normalize_header(h: str) -> str:
    """공백·괄호 등 정규화."""
    return re.sub(r"\s+", "", h).strip()


def _normalize_schema_header(header: str) -> str:
    return _normalize_header(header).casefold()


def classify_schema_columns(
    headers: Iterable[str],
) -> dict[str, SchemaColumnClassification]:
    """Classify schema columns without substring inference.

    Exact aliases receive confidence ``1.0`` and whitespace/case-normalized
    aliases receive ``0.95``. Generic names such as ``name`` or ``address`` are
    still returned as review evidence with confidence ``0.60``. Callers should
    set an explicit threshold when compiling a blocking SQL policy.
    """

    aliases: dict[str, list[tuple[str, str]]] = {}
    for alias, label in _HEADER_MAP.items():
        aliases.setdefault(_normalize_schema_header(alias), []).append((alias, label))

    classifications: dict[str, SchemaColumnClassification] = {}
    for header in headers:
        if not isinstance(header, str) or not header.strip():
            continue
        normalized = _normalize_schema_header(header)
        matches = aliases.get(normalized)
        if not matches:
            continue

        labels = {label for _, label in matches}
        if len(labels) != 1:
            # Conflicting aliases are unsafe to compile into a blocking policy.
            continue
        label = next(iter(labels))
        exact_alias = next((alias for alias, _ in matches if alias == header), None)
        match: Literal["exact", "normalized"] = (
            "exact" if exact_alias is not None else "normalized"
        )
        ambiguous = normalized in _SCHEMA_AMBIGUOUS_HEADERS
        confidence = 0.60 if ambiguous else (1.0 if match == "exact" else 0.95)
        classifications[header] = SchemaColumnClassification(
            column=header,
            label=label,
            confidence=confidence,
            match=match,
            matched_header=exact_alias or matches[0][0],
            ambiguous=ambiguous,
        )
    return classifications


_QUALIFIED_HEADER = re.compile(
    r"^(?:신청인|민원인|기안자|수신자|당사자|환자|고객|사용자|직원|담당자|보호자)[\s_-]*(.+)$"
    r"|^(?:applicant|patient|customer|user|employee)[\s_-]+(.+)$",
    re.IGNORECASE,
)


def map_columns(
    headers: Iterable[str], *, header_policy: Literal["conservative", "legacy"] = "conservative",
) -> dict[str, str]:
    """각 헤더에 대해 추정 PII 라벨 반환 (없으면 키 부재).

    >>> map_columns(["성명", "주민번호", "메모"])
    {'성명': 'PERSON', '주민번호': 'RRN'}

    By default, match aliases exactly (ignoring whitespace/case), or a known
    subject qualifier followed by an exact alias, such as ``신청인 연락처``.
    Unknown or mixed fields are left unmapped. Use an explicit ``column_map``
    for domain-specific headers. ``header_policy="legacy"`` restores the old
    first-substring behavior, including its possible false positives.
    """
    if header_policy not in {"conservative", "legacy"}:
        raise ValueError(f"Unknown header_policy: {header_policy}")
    mapping: dict[str, str]
    if header_policy == "conservative":
        names = list(headers)
        mapping = {h: c.label for h, c in classify_schema_columns(names).items()}
        for h in names:
            if h in mapping or not isinstance(h, str):
                continue
            match = _QUALIFIED_HEADER.fullmatch(h.strip())
            if match is not None:
                field = match.group(1) or match.group(2)
                classified = classify_schema_columns([field])
                if field in classified:
                    mapping[h] = classified[field].label
        return mapping

    mapping = {}
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
        from ko_pii.modes.fpe import _pseudonymize_value
        fp = vault.fingerprint(label, value)
        new_val = _pseudonymize_value(label, value, fp)
        vault.store(label, value, int(risk), legal_basis=legal_basis_for(label),
                    extra={"fpe_value": new_val})
        return new_val
    return value


def anonymize_value(
    value: str,
    label: str,
    *,
    strategy: str = "tokenize",
    vault: Optional[ReversibleVault] = None,
) -> tuple[str, ReversibleVault]:
    """Anonymize an explicitly typed value without detector inference.

    This is intended for schema-aware database results where upstream lineage
    already established the PII label. It must not be used to label unknown
    free text.
    """

    if not isinstance(value, str):
        raise TypeError(f"value must be str, got {type(value).__name__}")
    if not _valid_cell_label(label):
        raise ValueError("label must be nonempty and contain no token delimiters or newlines")
    if strategy not in {"tokenize", "redact", "asterisk", "partial", "hashed", "fpe"}:
        raise ValueError(f"Unknown strategy: {strategy}")
    active_vault = vault if vault is not None else ReversibleVault()
    return _force_anonymize_cell(value, label, strategy, active_vault), active_vault


def _valid_cell_label(label: object) -> bool:
    return isinstance(label, str) and bool(label.strip()) and not any(c in label for c in "<>\r\n")


def _table_records(records: Sequence[Mapping[Any, object]]) -> list[dict[str | None, object]]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("records must be a sequence of row mappings")
    checked: list[dict[str | None, object]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"record {index} must be a row mapping")
        row: dict[str | None, object] = {}
        for header, value in record.items():
            if header is None:
                if not isinstance(value, list) or any(item is not None and type(item) is not str for item in value):
                    raise ValueError(f"record {index} CSV overflow must be a list of strings or null")
                row[header] = list(value)
                continue
            if not isinstance(header, str):
                raise ValueError(f"record {index} column names must be strings")
            if value is not None and type(value) not in (str, int, float, bool):
                raise ValueError(f"record {index} cells must be scalars; use anonymize_json for nested data")
            if type(value) is float and not math.isfinite(value):
                raise ValueError(f"record {index} cells must contain finite numbers")
            row[header] = value
        checked.append(row)
    return checked


def anonymize_records(
    records: Sequence[Mapping[Any, object]],
    *,
    column_map: Optional[dict[str, str]] = None,
    mode: ProcessingMode = ProcessingMode.STRICT,
    strategy: str = "tokenize",
    vault: Optional[ReversibleVault] = None,
    header_policy: Literal["conservative", "legacy"] = "conservative",
) -> tuple[list[dict[str | None, object]], ReversibleVault]:
    """레코드(표) 단위 가명화 — 같은 구조 유지.

    Parameters
    ----------
    records : sequence of mappings
        ``read_records`` 등에서 얻은 행 데이터. 매핑된 셀은 문자열/정수/null이며,
        비매핑 셀은 일반 스칼라를 보존한다. 중첩 값은 JSON API를 사용한다.
    column_map : optional dict
        ``{header: label}`` 매핑 명시. 미지정 시 ``map_columns`` 로 자동 추론.
        비어 있지 않은 입력에서 어느 행에도 없는 명시적 열은 오류로 처리한다.
    mode, strategy, vault :
        ``AUDIT`` preserves cells and does not write to the Vault. In other
        modes, mapped columns are explicit label assertions and bypass detector
        thresholds. Asserted integers become strings only when transformed.
        Only the ``None`` CSV overflow key may contain a list of strings/null; these
        unnamed cells use :class:`Anonymizer` detection policies.
    header_policy :
        Automatic mapping policy (see :func:`map_columns`). An explicit
        ``column_map`` takes precedence, including an empty mapping.

    Returns
    -------
    (anonymized_records, vault) :
        같은 dict 구조의 가명화 결과 + 공유된 vault.
        매핑된 컬럼 *외* 의 값들은 원본 그대로 보존.
    """
    if header_policy not in {"conservative", "legacy"}:
        raise ValueError(f"Unknown header_policy: {header_policy}")
    checked = _table_records(records)
    if column_map is not None:
        if not isinstance(column_map, dict) or any(
            not isinstance(key, str) or not key.strip()
            or not _valid_cell_label(label)
            for key, label in column_map.items()
        ):
            raise ValueError("column_map must map non-empty column names to valid labels without token delimiters or newlines")
        if checked and any(not any(key in rec for rec in checked) for key in column_map):
            raise ValueError("column_map contains columns absent from the records")

    if column_map is None:
        # 전체 레코드 키의 합집합에서 추론 — records[0] 만 보면 희소/이질 레코드의
        # PII 컬럼이 미매핑돼 평문 통과한다 (#10).
        all_keys: set[str] = set()
        for r in checked:
            all_keys.update(k for k in r.keys() if isinstance(k, str))
        column_map = map_columns(all_keys, header_policy=header_policy)

    # Validate the entire table before any transformation can write to a Vault.
    for index, record in enumerate(checked):
        for header, value in record.items():
            if header is None or header not in column_map or value is None:
                continue
            if type(value) not in (str, int):
                raise ValueError(f"record {index} mapped cells must be strings, integers or null")
            try:
                text = str(value)
            except ValueError:
                raise ValueError(f"record {index} integer exceeds conversion limits") from None
            if mode != ProcessingMode.AUDIT:
                record[header] = text

    auto = Anonymizer(mode=mode, strategy=strategy, vault=vault)
    vault = auto.vault
    if mode == ProcessingMode.AUDIT:
        return checked, vault
    out: list[dict[str | None, object]] = []
    for rec in checked:
        new_rec: dict[str | None, object] = {}
        for header, value in rec.items():
            if header is None and isinstance(value, list):
                # csv.DictReader restkey: 헤더보다 셀이 많은 ragged row 의 초과 셀이
                # list 로 수집됨. 정상 컬럼이 아니라 *초과 셀* 이므로 자동 검출로
                # 스캔해 평문 PII 통과를 막는다 (#11).
                new_rec[header] = [
                    auto.process(v).text if isinstance(v, str) and v else v
                    for v in value
                ]
                continue
            label = column_map.get(header) if header is not None else None
            if not label or value is None or value == "":
                new_rec[header] = value
                continue
            # 컬럼 매핑 = 명시적 라벨 단언 → 검출기 임계값 우회
            assert isinstance(value, str)
            new_rec[header] = _force_anonymize_cell(value, label, strategy, vault)
        out.append(new_rec)

    return out, vault
