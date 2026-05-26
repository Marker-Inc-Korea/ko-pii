"""Legal mapping — PII category ↔ 법조항 단일 매핑 소스."""
from ko_pii.legal.mapping import (
    LEGAL_BASIS_BY_LABEL,
    CATEGORY_BY_LABEL,
    risk_floor_for,
    legal_basis_for,
    category_for,
)

__all__ = [
    "LEGAL_BASIS_BY_LABEL",
    "CATEGORY_BY_LABEL",
    "risk_floor_for",
    "legal_basis_for",
    "category_for",
]
