"""Passport formats from MOFA/Purview, not fitted to evaluation corpus rows."""
import re

import pytest

from ko_pii import Anonymizer, detect_all
from ko_pii.core.unicode_norm import normalize_unicode
from ko_pii.patterns.passport import detect
from ko_pii.tabular import anonymize_value
from ko_pii.vault.reversible import ReversibleVault


def _vault():
    return ReversibleVault(salt="passport", secret_key="test", fingerprint_iterations=1)


def _variant(value, form):
    if form == "fullwidth":
        return "".join(chr(ord(ch) + 0xFEE0) for ch in value)
    if form == "invisible":
        return value[:3] + "\u200b" + value[3:]
    return value


@pytest.mark.parametrize("prefix", list("MSROD"))
@pytest.mark.parametrize("serial", ["12345678", "123A4567", "123B4567", "123O4567"])
def test_literal_formats(prefix, serial):
    value = prefix + serial
    found = list(detect(value))
    assert len(found) == 1 and found[0].text == value
    assert found[0].extra["prefix"] == prefix
    assert found[0].extra["number"] == serial
    pipeline = detect_all(value, include=["PASSPORT"])
    assert len(pipeline) == 1 and pipeline[0].text == value


@pytest.mark.parametrize("value", ["M123A4567", "S123B4567", "O123G4567", "S12345678", "G12345678"])
@pytest.mark.parametrize("form", ["ascii", "fullwidth", "invisible"])
def test_pipeline_preserves_letters_and_source_offsets(value, form):
    raw = _variant(value, form)
    prefix, suffix = "\ufb01 \U0001f512 passport: ", " [end]"
    source = prefix + raw + suffix
    found = detect_all(source, include=["PASSPORT"])
    assert len(found) == 1
    detection = found[0]
    assert (detection.start, detection.end, detection.text) == (len(prefix), len(prefix) + len(raw), raw)
    assert detection.rule_id == "ko-pii.passport.v1"
    result = Anonymizer(strategy="redact", include=["PASSPORT"]).process(source)
    assert result.text == prefix + "[\uc5ec\uad8c\ubc88\ud638]" + suffix


@pytest.mark.parametrize("value", ["M123A4567", "S123B4567", "O123G4567"])
@pytest.mark.parametrize("entry", ["detected", "typed"])
@pytest.mark.parametrize("strategy", ["tokenize", "partial", "fpe"])
def test_modern_passport_transforms(value, entry, strategy):
    vault = _vault()
    if entry == "typed":
        output, _ = anonymize_value(value, "PASSPORT", strategy=strategy, vault=vault)
    else:
        output = Anonymizer(strategy=strategy, include=["PASSPORT"], vault=vault).process(value).text
    assert output != value
    if strategy == "partial":
        assert output == value[0] + "******" + value[-2:]
    elif strategy == "fpe":
        assert re.fullmatch(value[0] + r"[0-9]{3}[A-Z][0-9]{4}", output)
        assert vault.entries()[0].original == value
        assert vault.entries()[0].extra["fpe_value"] == output
    else:
        assert output == "<PASSPORT_1>"
        assert vault.reveal(output) == value


@pytest.mark.parametrize("value", [
    "PP12345678", "PO12345678", "PM12345678", "PT12345678",
    "M12A45678", "M1234A567", "M123a4567", "m123A4567",
    "M123A456", "M123A45678", "XM123A4567", "M123A4567X", "X123A4567",
])
def test_non_number_codes_and_wrong_shapes_are_not_passports(value):
    assert list(detect(value)) == []
    assert detect_all(value, include=["PASSPORT"]) == []


def test_filters_and_explicit_normalization_opt_out():
    assert detect_all("S123B4567", exclude=["PASSPORT"]) == []
    assert detect_all("S123B4567", include=["EMAIL"]) == []
    assert len(detect_all("S123B4567", include=["PASSPORT"], normalize=False)) == 1
    assert detect_all(_variant("S123B4567", "fullwidth"), include=["PASSPORT"], normalize=False) == []


def test_numeric_anti_evasion_is_not_disabled():
    # This can also look like a legacy passport. The PHONE-only path must remain.
    assert normalize_unicode("O21234567")[0] == "021234567"
    assert len(detect_all("O21234567", include=["PHONE"])) == 1
    for value in ["010-12O4-5678", "8801O1-1234568"]:
        assert Anonymizer(strategy="redact").process(value).text != value


def test_literal_letter_view_keeps_unicode_mapping():
    raw = _variant("S123B4567", "fullwidth")
    assert normalize_unicode(raw, fold_numeric=False) == ("S123B4567", list(range(9)))
    assert normalize_unicode("S123B4567", fold_numeric=False) == ("S123B4567", [])


def test_multiple_passports_and_neighboring_numeric_pii():
    source = "S123B4567 / O12345678 / 010-12O4-5678"
    found = detect_all(source)
    assert [(d.label, d.text) for d in found] == [
        ("PASSPORT", "S123B4567"), ("PASSPORT", "O12345678"), ("PHONE", "010-12O4-5678"),
    ]


@pytest.mark.parametrize("strategy", ["partial", "fpe"])
def test_compound_typed_passport_field_is_fully_masked(strategy):
    value = "M123A4567 / Private Person"
    assert anonymize_value(value, "PASSPORT", strategy=strategy, vault=_vault())[0] == "*" * len(value)
