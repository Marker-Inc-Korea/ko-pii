"""Typed transforms must not preserve prose as numeric formatting."""
import re

import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.field_rules import FieldRule
from ko_pii.modes.fpe import fpe
from ko_pii.modes.partial import mask_value, partial
from ko_pii.profile import PolicyProfile
from ko_pii.structured import anonymize_json
from ko_pii.tabular import anonymize_records, anonymize_value
from ko_pii.vault.reversible import ReversibleVault


def _transform(label, value, strategy, entry):
    vault = ReversibleVault(salt="test", secret_key="test", fingerprint_iterations=1)
    anon = Anonymizer(strategy=strategy, vault=vault)
    if entry == "value":
        return anonymize_value(value, label, strategy=strategy, vault=vault)[0]
    if entry == "records":
        return anonymize_records(
            [{"field": value}], column_map={"field": label}, strategy=strategy, vault=vault,
        )[0][0]["field"]
    if entry == "profile":
        profile = PolicyProfile({"strategy": strategy, "field_labels": {"/field": label}})
        return profile.process_json({"field": value}).data["field"]
    if entry in {"json", "rules"}:
        options = ({"field_labels": {"/field": label}} if entry == "json"
                   else {"field_rules": [FieldRule(("field",), label)]})
        result = anonymize_json({"field": value}, anonymizer=anon, **options)
        assert result.fields[0].result.substitutions[0].end == len(value)
        return result.data["field"]
    detections = [DetectionResult(label, value, 0, len(value), RiskLevel.HIGH)]
    return fpe(value, detections, vault=vault)[0] if strategy == "fpe" else partial(value, detections)


@pytest.mark.parametrize("entry", ["value", "records", "json", "rules", "span", "profile"])
@pytest.mark.parametrize(("label", "value", "strategy"), [
    ("PHONE", "010-1234-5678 (\ud64d\uae38\ub3d9)", "fpe"),
    ("FAX", "02-1234-5678 / secret@example.com", "fpe"),
    ("CARD", "4111-1111-1111-1111 (\ud64d\uae38\ub3d9)", "fpe"),
    ("CARD", "4111-1111-1111-1111 / secret@example.com", "fpe"),
    ("DT_BIRTH", "\ud64d\uae38\ub3d9 / 010-1234-5678 / 1988\ub144\uc0dd", "partial"),
    ("PERSON", "\ud64d", "partial"),
    ("PERSON", "\ub0a8\uad81", "partial"),
    ("PASSPORT", "M1", "partial"),
    ("PASSPORT", "M12", "partial"),
])
def test_compound_or_too_short_values_are_masked(entry, label, value, strategy):
    assert _transform(label, value, strategy, entry) == "*" * len(value)


@pytest.mark.parametrize("label", ["PHONE", "FAX", "CARD"])
@pytest.mark.parametrize("suffix", [
    " (Private Person)", "\nsecret@example.com", "\t\uc7a5\uc740\uc218", "\U0001f512", " ext: 1234",
])
def test_fpe_numeric_formatting_never_preserves_appended_content(label, suffix):
    number = "4111-1111-1111-1111" if label == "CARD" else "010-1234-5678"
    value = number + suffix
    assert _transform(label, value, "fpe", "value") == "*" * len(value)


@pytest.mark.parametrize(("label", "value"), [
    ("PHONE", "010-1234-5678 010-2345-6789"),
    ("CARD", "4111111111111111/4242424242424242"),
    ("CARD", "12345678"),
    ("PHONE", "123456"),
    ("PHONE", "\uff10\uff11\uff10-\uff11\uff12\uff13\uff14-\uff15\uff16\uff17\uff18 (\ufb01 Private)"),
])
def test_fpe_unsupported_numeric_fields_use_original_length(label, value):
    assert _transform(label, value, "fpe", "value") == "*" * len(value)


@pytest.mark.parametrize(("label", "value"), [
    ("PHONE", "010-1234-5678"), ("PHONE", "(02) 1234-5678"),
    ("FAX", "031)123-4567"), ("PHONE", "+82 (0)10-1234-5678"),
    ("PHONE", "1588-1234"), ("PHONE", "0504-1234-5678"),
    ("CARD", "4111.1111.1111.1111"), ("CARD", "4111 /1111 /1111 /1111"),
    ("CARD", "3782 822463 10005"),
])
def test_fpe_supported_numeric_formatting_stays_compatible(label, value):
    result = _transform(label, value, "fpe", "value")
    assert result != value and "*" not in result
    if len(re.sub(r"\D", "", value)) >= 9:
        assert len(result) == len(value)
        assert re.sub(r"[0-9]", "#", result) == re.sub(r"[0-9]", "#", value)


@pytest.mark.parametrize(("label", "value", "expected"), [
    ("PERSON", "\ud64d\uae38\ub3d9", "\ud64dOO"),
    ("PERSON", "\ub0a8\uad81\ubbfc\uc218", "\ub0a8\uad81OO"),
    ("PASSPORT", "M12345678", "M******78"),
    ("DT_BIRTH", "88\ub144\uc0dd", "88\ub144\uc0dd"),
    ("DT_BIRTH", "1988\ub144\uc0dd", "1988\ub144\uc0dd"),
    ("DT_BIRTH", "1988-01-01", "1988-**-**"),
    ("POSITION", "\uc0ac\ubb34\uad00", "\uc0ac\ubb34\uad00"),
])
def test_partial_retention_is_limited_to_documented_shapes(label, value, expected):
    assert mask_value(label, value) == expected


@pytest.mark.parametrize("value", ["\ud64d", "\ub0a8\uad81", "X"])
def test_direct_partial_name_helper_masks_short_values(value):
    assert mask_value("PERSON", value) == "*" * len(value)


@pytest.mark.parametrize("value", ["M1", "M12", "M12\n", "PP12"])
def test_direct_partial_passport_helper_masks_short_values(value):
    assert mask_value("PASSPORT", value) == "*" * len(value)


def test_audit_still_preserves_raw_asserted_fields():
    value = "010-1234-5678 (Private Person)"
    result = anonymize_json(
        {"phone": value}, field_labels={"/phone": "PHONE"},
        anonymizer=Anonymizer(mode=ProcessingMode.AUDIT, strategy="fpe"),
    )
    assert result.data["phone"] == value
    assert result.fields[0].result.substitutions == []


def test_fpe_fallback_records_original_and_masked_value_in_vault():
    value = "010-1234-5678 (Private Person)"
    vault = ReversibleVault(salt="test", secret_key="test", fingerprint_iterations=1)
    output, returned = anonymize_value(value, "PHONE", strategy="fpe", vault=vault)
    assert returned is vault and output == "*" * len(value)
    assert vault.entries()[0].original == value
    assert vault.entries()[0].extra["fpe_value"] == output
