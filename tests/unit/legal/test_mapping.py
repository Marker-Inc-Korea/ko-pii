from ko_pii.core.types import RiskLevel
from ko_pii.legal.mapping import (
    LEGAL_BASIS_BY_LABEL,
    CATEGORY_BY_LABEL,
    legal_basis_for,
    category_for,
    risk_floor_for,
)


def test_rrn_legal_basis():
    assert legal_basis_for("RRN") == "개인정보보호법 제24조의2"


def test_corp_reg_legal_basis():
    assert legal_basis_for("CORP_REG") == "상법 제40조"


def test_category_for_known_labels():
    assert category_for("RRN") == "고유식별정보"
    assert category_for("CARD") == "금융정보"
    assert category_for("MEDICAL_INSURANCE") == "민감정보(건강)"


def test_risk_floor():
    assert risk_floor_for("RRN") == RiskLevel.CRITICAL
    assert risk_floor_for("URL") == RiskLevel.INFO
    assert risk_floor_for("UNKNOWN") is None


def test_legal_basis_matches_pattern_modules():
    # Sanity: a few keys exist for all the labels we implement.
    must_have = {
        "RRN", "FRN", "BUSINESS_REG", "CORP_REG", "DRIVER_LICENSE",
        "PASSPORT", "CARD", "MEDICAL_INSURANCE", "PHONE", "EMAIL",
        "POSTAL_CODE", "IP", "VEHICLE", "URL", "ADDRESS", "ACCOUNT",
        "PERSON",
    }
    assert must_have.issubset(LEGAL_BASIS_BY_LABEL.keys())
    assert must_have.issubset(CATEGORY_BY_LABEL.keys())
