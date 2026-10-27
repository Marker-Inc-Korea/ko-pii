"""Independent fixed vectors for legacy FRN arithmetic; all data synthetic."""
import random

import pytest

from ko_pii.checksum.frn_checksum import compute_check_digit, is_valid_checksum


# Complement-weight residues 0..10, including both exceptional reductions.
@pytest.mark.parametrize("prefix, expected", [
    ("850315500001", 3), ("850315500003", 3), ("850315500005", 4),
    ("850315500007", 5), ("850315500009", 6), ("850315500000", 7),
    ("850315500002", 8), ("850315500004", 9), ("850315500006", 0),
    ("850315500008", 1), ("850315500017", 2),
    ("850315534567", 8), ("850315524567", 6), ("850315600000", 0),
    ("000101700000", 1), ("000101800000", 3),
])
def test_fixed_vectors_and_every_wrong_digit(prefix, expected):
    assert compute_check_digit(prefix) == expected
    for digit in range(10):
        assert is_valid_checksum(prefix + str(digit)) is (digit == expected)


@pytest.mark.parametrize("value", [
    "", "85031553456", "8503155345678", "850315-53456", "85031553456x",
    "\uff18" * 12, "\u0668" * 12, "\u00b2" * 12, None, 850315534567,
])
def test_compute_rejects_non_ascii_or_wrong_shape(value):
    with pytest.raises(ValueError, match="12-digit ASCII"):
        compute_check_digit(value)


@pytest.mark.parametrize("value", [
    "", "850315534567", "85031553456789", "850315-5345678", "850315534567x",
    "\uff18" * 13, "\u0668" * 13, "\u00b2" * 13, None, 8503155345678,
])
def test_validation_returns_false_for_malformed_values(value):
    assert is_valid_checksum(value) is False


def test_generated_vectors_against_complement_weight_oracle():
    rng = random.Random(20261027)
    for _ in range(1000):
        prefix = "".join(str(rng.randrange(10)) for _ in range(12))
        remainder = sum(int(d) * (9 - i % 8) for i, d in enumerate(prefix)) % 11
        expected = ({0: 1, 10: 0}.get(remainder, remainder) + 2) % 10
        assert compute_check_digit(prefix) == expected
