"""사업자등록번호 (Business Registration Number) checksum validation.

10-digit format: XXX-YY-NNNNN. The 10th digit is the check digit.

Algorithm (per 국세청 specification):
  weights = (1, 3, 7, 1, 3, 7, 1, 3, 5) applied to digits 1..9.
  Additionally, (digit[8] * 5) // 10 is added to the weighted sum.
  check = (10 - sum % 10) % 10
"""
from __future__ import annotations

WEIGHTS: tuple[int, ...] = (1, 3, 7, 1, 3, 7, 1, 3, 5)


def compute_check_digit(nine_digits: str) -> int:
    if len(nine_digits) != 9 or not nine_digits.isdigit():
        raise ValueError("expected a 9-digit numeric string")
    total = sum(int(d) * w for d, w in zip(nine_digits, WEIGHTS))
    total += (int(nine_digits[8]) * 5) // 10
    return (10 - total % 10) % 10


def is_valid_checksum(ten_digits: str) -> bool:
    if len(ten_digits) != 10 or not ten_digits.isdigit():
        return False
    return compute_check_digit(ten_digits[:9]) == int(ten_digits[9])
