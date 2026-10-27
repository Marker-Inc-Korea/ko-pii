"""Typed table columns must not fall back to free-text inference."""
from copy import deepcopy

import pytest

from ko_pii import ProcessingMode
from ko_pii.tabular import anonymize_records, anonymize_value
from ko_pii.vault.reversible import ReversibleVault


STRATEGIES = ["tokenize", "redact", "asterisk", "partial", "hashed", "fpe"]


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("value", [0, 12345, -17])
def test_asserted_integer_matches_explicit_string_transformation(strategy, value):
    vault = ReversibleVault()
    expected, _ = anonymize_value(str(value), "ACCOUNT", strategy=strategy, vault=vault)
    original = [{"account": value, "count": 7}]
    output, returned = anonymize_records(
        original, column_map={"account": "ACCOUNT"}, strategy=strategy, vault=vault,
    )
    assert output == [{"account": expected, "count": 7}]
    assert isinstance(output[0]["account"], str)
    assert returned is vault
    assert original == [{"account": value, "count": 7}]


@pytest.mark.parametrize("mode", [mode for mode in ProcessingMode if mode != ProcessingMode.AUDIT])
def test_all_transforming_modes_apply_zero_identifier_assertion(mode):
    output, _ = anonymize_records([{"rrn": 0}], mode=mode, strategy="redact")
    assert output == [{"rrn": "[\uc8fc\ubbfc\ub4f1\ub85d\ubc88\ud638]"}]


def test_audit_keeps_integer_type_and_does_not_store():
    rows = [{"account": 0}, {"account": 12345}, {"account": None}]
    vault = ReversibleVault()
    output, returned = anonymize_records(
        rows, column_map={"account": "ACCOUNT"}, mode=ProcessingMode.AUDIT, vault=vault,
    )
    assert output == rows and type(output[0]["account"]) is int
    assert returned is vault and len(vault) == 0


def test_integer_and_string_same_identifier_share_token_without_trimming_strings():
    rows = [{"account": 12345}, {"account": "12345"}, {"account": "0012345"}]
    output, vault = anonymize_records(rows, column_map={"account": "ACCOUNT"})
    assert output[0] == output[1] and output[1] != output[2]
    assert vault.reveal(output[0]["account"]) == "12345"
    assert vault.reveal(output[2]["account"]) == "0012345"


@pytest.mark.parametrize("explicit", [True, False])
@pytest.mark.parametrize("value", [
    ["synthetic-person"], {"nested": "synthetic-person"}, ("synthetic-person",),
    True, False, 0.0, 123.0, float("inf"), b"synthetic-person",
])
def test_invalid_typed_cell_is_rejected_before_any_vault_write(explicit, value):
    rows = [{"name": "first-synthetic-person"}, {"name": value}]
    before = deepcopy(rows)
    vault = ReversibleVault()
    with pytest.raises(ValueError) as error:
        anonymize_records(rows, column_map={"name": "PERSON"} if explicit else None, vault=vault)
    assert "synthetic-person" not in str(error.value)
    assert len(vault) == 0 and rows == before


@pytest.mark.parametrize("mode", list(ProcessingMode))
def test_nested_asserted_field_never_uses_free_text_detection(mode):
    with pytest.raises(ValueError):
        anonymize_records([{"name": ["synthetic-person"]}], mode=mode)


def test_unmapped_scalar_types_and_null_empty_cells_are_preserved():
    rows = [{"email": "", "count": 7, "ratio": 0.5, "enabled": False, "extra": None},
            {"email": None, "count": 0}]
    output, vault = anonymize_records(rows)
    assert output == rows and len(vault) == 0
    assert output is not rows and output[0] is not rows[0]


@pytest.mark.parametrize("value", [["synthetic-person"], {"nested": "synthetic-person"}])
def test_nested_unmapped_columns_require_structured_api(value):
    vault = ReversibleVault()
    with pytest.raises(ValueError):
        anonymize_records([{"email": "synthetic@example.com"}, {"memo": value}], vault=vault)
    assert len(vault) == 0


def test_csv_overflow_remains_detector_based_and_does_not_alias_input():
    rows = [{"email": "first@example.com", None: ["second@example.com", "", "public", None]}]
    before = deepcopy(rows)
    output, _ = anonymize_records(rows, strategy="redact")
    assert "@example.com" not in repr(output)
    assert output[0][None][1:] == ["", "public", None]
    assert rows == before and output[0][None] is not rows[0][None]


@pytest.mark.parametrize("value", [None, "synthetic-person", [12345], [False], [["synthetic-person"]]])
def test_invalid_csv_overflow_is_rejected_before_any_vault_write(value):
    vault = ReversibleVault()
    with pytest.raises(ValueError) as error:
        anonymize_records([{"email": "synthetic@example.com"}, {None: value}], vault=vault)
    assert "synthetic" not in str(error.value) and len(vault) == 0


@pytest.mark.parametrize("rows", [None, "synthetic-person", [None], [12345], [["synthetic-person"]]])
def test_invalid_record_container_is_rejected_without_reflecting_input(rows):
    with pytest.raises(ValueError) as error:
        anonymize_records(rows)
    assert "synthetic-person" not in str(error.value)


@pytest.mark.parametrize("header", [123, ("synthetic-person",)])
def test_nonstring_header_is_not_silently_unmapped(header):
    vault = ReversibleVault()
    with pytest.raises(ValueError):
        anonymize_records([{"email": "synthetic@example.com"}, {header: "synthetic-person"}], vault=vault)
    assert len(vault) == 0


def test_empty_table_still_validates_strategy():
    with pytest.raises(ValueError, match="strategy"):
        anonymize_records([], strategy="typo")


@pytest.mark.parametrize("label", ["PERSON\nSECRET", "<PERSON", "PERSON>", "PERSON\rSECRET"])
def test_invalid_mapping_label_fails_before_prior_cells_are_stored(label):
    vault = ReversibleVault()
    with pytest.raises(ValueError) as error:
        anonymize_records(
            [{"email": "synthetic@example.com", "other": "synthetic-person"}],
            column_map={"email": "EMAIL", "other": label}, vault=vault,
        )
    assert len(vault) == 0 and "SECRET" not in str(error.value)
    with pytest.raises(ValueError):
        anonymize_value("synthetic-person", label, strategy="redact", vault=vault)


def test_custom_typed_label_remains_supported():
    output, vault = anonymize_records([{"id": 12345}], column_map={"id": "CUSTOM_ID"})
    assert output[0]["id"] == "<CUSTOM_ID_1>"
    assert vault.reveal(output[0]["id"]) == "12345"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_unmapped_number_is_rejected_before_store(value):
    vault = ReversibleVault()
    with pytest.raises(ValueError):
        anonymize_records([{"email": "synthetic@example.com", "ratio": value}], vault=vault)
    assert len(vault) == 0


def test_large_integer_conversion_fails_before_prior_rows_are_stored():
    import sys

    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("integer conversion limit is unavailable")
    previous = sys.get_int_max_str_digits()
    vault = ReversibleVault()
    try:
        sys.set_int_max_str_digits(640)
        with pytest.raises(ValueError):
            anonymize_records(
                [{"account": "12345"}, {"account": 10 ** 700}],
                column_map={"account": "ACCOUNT"}, vault=vault,
            )
        assert len(vault) == 0
    finally:
        sys.set_int_max_str_digits(previous)
