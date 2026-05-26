"""Irreversible redaction (masking) mode.

원본 정보는 복원 불가하며, 카테고리 라벨 ``[성명]`` 또는 ``***`` 류 마스크로
치환된다. 정보 분석/저장 대상이 *아닌* 표시·공유 용도 사용.

Legal basis: 개인정보보호법 비식별 조치 가이드라인 — 가명처리(가역) 와 비식별
(비가역) 구분.
"""
from __future__ import annotations

from typing import Iterable

from ko_pii.core.types import DetectionResult
from ko_pii.modes._apply import apply_substitutions

_LABEL_TO_HANGUL: dict[str, str] = {
    "RRN": "주민등록번호",
    "FRN": "외국인등록번호",
    "BUSINESS_REG": "사업자등록번호",
    "CORP_REG": "법인등록번호",
    "DRIVER_LICENSE": "운전면허번호",
    "PASSPORT": "여권번호",
    "CARD": "카드번호",
    "MEDICAL_INSURANCE": "건강보험증번호",
    "PHONE": "전화번호",
    "FAX": "팩스번호",
    "EMAIL": "이메일",
    "POSTAL_CODE": "우편번호",
    "IP": "IP",
    "VEHICLE": "차량번호",
    "URL": "URL",
    "ADDRESS": "주소",
    "ACCOUNT": "계좌번호",
    "PERSON": "성명",
    "DOC_ID": "문서번호",
    "PETITION_ID": "민원번호",
    "EMPLOYEE_ID": "사번",
    "PNU": "토지번호",
    "PRESCRIPTION_ID": "처방번호",
    "EDI_DRUG": "약품코드",
    "DT_BIRTH": "생년월일",
    "EDUCATION": "학력",
    "MAJOR": "전공",
    "POSITION": "직책",
    "AGE": "나이",
    "HEIGHT": "신장",
    "WEIGHT": "체중",
    "COURT_CASE": "사건번호",
}


def label_to_hangul(label: str) -> str:
    return _LABEL_TO_HANGUL.get(label, label)


def redact(
    text: str,
    detections: Iterable[DetectionResult],
    style: str = "label",
    mask_char: str = "*",
) -> str:
    """Replace each detection span with an irreversible mask.

    ``style``:
      - ``"label"``  — ``[성명]``, ``[주민등록번호]`` (default)
      - ``"asterisk"`` — repeat ``mask_char`` * len(match)
      - ``"fixed"``  — fixed ``***`` regardless of length
    """
    if style not in {"label", "asterisk", "fixed"}:
        raise ValueError(f"Unknown redact style: {style}")

    def _replace(d):
        if style == "label":
            return f"[{label_to_hangul(d.label)}]"
        if style == "asterisk":
            return mask_char * max(1, d.end - d.start)
        return "***"

    return apply_substitutions(text, detections, _replace)
