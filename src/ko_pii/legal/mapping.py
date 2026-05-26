"""PII 카테고리 ↔ 한국 법조항 매핑 (단일 진실 소스).

각 검출 결과의 ``legal_basis`` 는 해당 모듈에서 직접 부여되지만, 본 매핑은
보고서·증명서 생성 등에서 라벨만으로 법조항을 조회할 때 사용한다.
"""
from __future__ import annotations

from typing import Optional

from ko_pii.core.types import RiskLevel

LEGAL_BASIS_BY_LABEL: dict[str, str] = {
    # 고유식별정보
    "RRN": "개인정보보호법 제24조의2",
    "FRN": "개인정보보호법 시행령 제19조; 출입국관리법 제31조",
    "PASSPORT": "개인정보보호법 시행령 제19조",
    "DRIVER_LICENSE": "개인정보보호법 시행령 제19조; 도로교통법 제80조",
    # 등록정보
    "BUSINESS_REG": "법인세법; 부가가치세법",
    "CORP_REG": "상법 제40조",
    # 금융
    "CARD": "여신전문금융업법; 개인정보보호법 제2조",
    "ACCOUNT": "금융실명거래 및 비밀보장에 관한 법률",
    # 건강
    "MEDICAL_INSURANCE": "국민건강보험법 제96조",
    # 일반 식별
    "PHONE": "개인정보보호법 제2조",
    "FAX": "개인정보보호법 제2조",
    "EMAIL": "개인정보보호법 제2조",
    "POSTAL_CODE": "개인정보보호법 제2조",
    "IP": "개인정보보호법 제2조",
    "VEHICLE": "개인정보보호법 제2조; 자동차관리법",
    "URL": "—",
    "ADDRESS": "개인정보보호법 제2조",
    # 컨텍스트 기반 (Phase 3)
    "PERSON": "개인정보보호법 제2조",
    # 도메인 특화 (Phase 4)
    "DOC_ID": "개인정보보호법 제2조",
    "PETITION_ID": "개인정보보호법 제2조; 민원처리에 관한 법률",
    "EMPLOYEE_ID": "개인정보보호법 제2조; 국가공무원법 제22조",
    "PNU": "공간정보의 구축 및 관리 등에 관한 법률; 개인정보보호법 제2조",
    "PRESCRIPTION_ID": "의료법 제18조; 약사법 제22조; 개인정보보호법 제23조",
    "EDI_DRUG": "약사법 제31조; 개인정보보호법 제2조",
    "COURT_CASE": "개인정보보호법 제2조; 민사소송법 제65조",
    # 인적 속성 — 준식별자 (KDPII 분류 참조)
    "DT_BIRTH": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
    "EDUCATION": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
    "MAJOR": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
    "POSITION": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
    "AGE": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
    "HEIGHT": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
    "WEIGHT": "개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」 준식별자",
}

CATEGORY_BY_LABEL: dict[str, str] = {
    "RRN": "고유식별정보",
    "FRN": "고유식별정보",
    "PASSPORT": "고유식별정보",
    "DRIVER_LICENSE": "고유식별정보",
    "BUSINESS_REG": "법인/사업자 식별정보",
    "CORP_REG": "법인/사업자 식별정보",
    "CARD": "금융정보",
    "ACCOUNT": "금융정보",
    "MEDICAL_INSURANCE": "민감정보(건강)",
    "PHONE": "일반개인정보",
    "FAX": "일반개인정보",
    "EMAIL": "일반개인정보",
    "POSTAL_CODE": "일반개인정보",
    "IP": "일반개인정보",
    "VEHICLE": "일반개인정보",
    "URL": "참조정보",
    "ADDRESS": "일반개인정보",
    "PERSON": "일반개인정보",
    "DOC_ID": "참조정보",
    "PETITION_ID": "참조정보",
    "EMPLOYEE_ID": "일반개인정보",
    "PNU": "참조정보",
    "PRESCRIPTION_ID": "민감정보(건강)",
    "EDI_DRUG": "참조정보",
    "COURT_CASE": "참조정보",
    "DT_BIRTH": "준식별자",
    "EDUCATION": "준식별자",
    "MAJOR": "준식별자",
    "POSITION": "준식별자",
    "AGE": "준식별자",
    "HEIGHT": "준식별자",
    "WEIGHT": "준식별자",
}

_RISK_FLOOR_BY_LABEL: dict[str, RiskLevel] = {
    "RRN": RiskLevel.CRITICAL,
    "FRN": RiskLevel.CRITICAL,
    "PASSPORT": RiskLevel.CRITICAL,
    "DRIVER_LICENSE": RiskLevel.HIGH,
    "BUSINESS_REG": RiskLevel.LOW,
    "CORP_REG": RiskLevel.MEDIUM,
    "CARD": RiskLevel.CRITICAL,
    "ACCOUNT": RiskLevel.HIGH,
    "MEDICAL_INSURANCE": RiskLevel.HIGH,
    "PHONE": RiskLevel.MEDIUM,
    "FAX": RiskLevel.LOW,
    "EMAIL": RiskLevel.MEDIUM,
    "POSTAL_CODE": RiskLevel.LOW,
    "IP": RiskLevel.MEDIUM,
    "VEHICLE": RiskLevel.MEDIUM,
    "URL": RiskLevel.INFO,
    "ADDRESS": RiskLevel.MEDIUM,
    "PERSON": RiskLevel.HIGH,
    "DOC_ID": RiskLevel.LOW,
    "PETITION_ID": RiskLevel.LOW,
    "EMPLOYEE_ID": RiskLevel.MEDIUM,
    "PNU": RiskLevel.LOW,
    "PRESCRIPTION_ID": RiskLevel.HIGH,
    "EDI_DRUG": RiskLevel.LOW,
    "COURT_CASE": RiskLevel.MEDIUM,
    "DT_BIRTH": RiskLevel.HIGH,
    "EDUCATION": RiskLevel.MEDIUM,
    "MAJOR": RiskLevel.LOW,
    "POSITION": RiskLevel.LOW,
    "AGE": RiskLevel.INFO,
    "HEIGHT": RiskLevel.INFO,
    "WEIGHT": RiskLevel.INFO,
}


def legal_basis_for(label: str) -> Optional[str]:
    return LEGAL_BASIS_BY_LABEL.get(label)


def category_for(label: str) -> Optional[str]:
    return CATEGORY_BY_LABEL.get(label)


def risk_floor_for(label: str) -> Optional[RiskLevel]:
    """The expected minimum risk level for ``label`` (used in reports)."""
    return _RISK_FLOOR_BY_LABEL.get(label)
