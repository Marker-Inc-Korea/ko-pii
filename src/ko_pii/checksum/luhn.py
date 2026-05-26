"""Luhn algorithm (ISO/IEC 7812 mod-10 check) — used by credit/debit cards."""
from __future__ import annotations


def is_valid(digits: str) -> bool:
    """Return True if *digits* (an all-numeric string) passes Luhn's check."""
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d >= 10:
                d -= 9  # equivalent to sum of decimal digits of d
        total += d
    return total % 10 == 0


def compute_check_digit(payload: str) -> int:
    """Return the check digit that would make *payload* + check_digit valid."""
    if not payload.isdigit():
        raise ValueError("expected numeric string")
    total = 0
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        # Note: payload is the prefix, so when appending a check digit it
        # becomes position 0 (right-most). Position i in reversed(payload)
        # corresponds to position i+1 from the right in the full number.
        if i % 2 == 0:  # equivalent to "i+1 is odd" → doubled positions
            d *= 2
            if d >= 10:
                d -= 9
        total += d
    return (10 - total % 10) % 10
