"""법인등록번호 (Corporation Registration Number) checksum validation.

13-digit format: NNNNNN-NNNNNNN. The 13th digit is the check digit.

Algorithm (Luhn-like):
  weights = (1, 2) alternating across digits 1..12.
  For each digit*weight product p, add (p // 10) + (p % 10) — i.e., the sum
  of its decimal digits.
  check = (10 - sum % 10) % 10
"""
from __future__ import annotations

WEIGHTS: tuple[int, ...] = (1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2)


def compute_check_digit(twelve_digits: str) -> int:
    if len(twelve_digits) != 12 or not twelve_digits.isdigit():
        raise ValueError("expected a 12-digit numeric string")
    total = 0
    for d, w in zip(twelve_digits, WEIGHTS):
        product = int(d) * w
        total += (product // 10) + (product % 10)
    return (10 - total % 10) % 10


def is_valid_checksum(thirteen_digits: str) -> bool:
    if len(thirteen_digits) != 13 or not thirteen_digits.isdigit():
        return False
    return compute_check_digit(thirteen_digits[:12]) == int(thirteen_digits[12])
