"""주민등록번호 (RRN) checksum validation.

Algorithm: digits 1..12 are multiplied by weights (2,3,4,5,6,7,8,9,2,3,4,5),
summed, and the expected check digit equals (11 - sum % 11) % 10.

Caveat: 행정안전부 randomized the last 7 digits of newly issued RRNs starting
2020-10-05, so post-2020 RRNs may not satisfy this checksum. Treat a checksum
failure as reduced confidence, not as proof the value is not an RRN.
"""
from __future__ import annotations

WEIGHTS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)


def compute_check_digit(twelve_digits: str) -> int:
    """Return the expected 13th digit for the first 12 digits of an RRN."""
    if len(twelve_digits) != 12 or not twelve_digits.isdigit():
        raise ValueError("expected a 12-digit numeric string")
    total = sum(int(d) * w for d, w in zip(twelve_digits, WEIGHTS))
    return (11 - total % 11) % 10


def is_valid_checksum(thirteen_digits: str) -> bool:
    """Return True if the 13-digit RRN matches its check digit."""
    if len(thirteen_digits) != 13 or not thirteen_digits.isdigit():
        return False
    return compute_check_digit(thirteen_digits[:12]) == int(thirteen_digits[12])
