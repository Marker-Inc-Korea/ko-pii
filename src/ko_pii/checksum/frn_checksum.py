"""Legacy foreign-registration checksum arithmetic, not identity validation.

The foreign digit is the resident weighted-sum digit plus 2, modulo 10.
See docs/IDENTIFIER_VALIDATION.md for the reference and scope limitations.
Date, century and detector policy are deliberately separate from this helper.
"""
from __future__ import annotations

from ko_pii.checksum.rrn_checksum import compute_check_digit as resident_check_digit


def compute_check_digit(twelve_digits: str) -> int:
    """Return the legacy foreign check digit for exactly 12 ASCII digits."""
    if (not isinstance(twelve_digits, str) or len(twelve_digits) != 12
            or not twelve_digits.isascii() or not twelve_digits.isdigit()):
        raise ValueError("expected a 12-digit ASCII string")
    return (resident_check_digit(twelve_digits) + 2) % 10


def is_valid_checksum(thirteen_digits: str) -> bool:
    """Check the arithmetic only; a mismatch does not prove non-PII."""
    if (not isinstance(thirteen_digits, str) or len(thirteen_digits) != 13
            or not thirteen_digits.isascii() or not thirteen_digits.isdigit()):
        return False
    return compute_check_digit(thirteen_digits[:12]) == int(thirteen_digits[12])
