"""Detection and output strategies must agree on nonstandard numeric forms."""
import re

import pytest

from ko_pii import Anonymizer, detect_all
from ko_pii.core.unicode_norm import normalize_unicode
from ko_pii.modes.fpe import _FPE_BY_LABEL, _pseudonymize_value, fpe
from ko_pii.modes.partial import mask_value, partial
from ko_pii.tabular import anonymize_records, anonymize_value
from ko_pii.vault.reversible import ReversibleVault


def _vault():
    # Only speed up the test fixture's KDF; production defaults are unchanged.
    return ReversibleVault(salt="regression", secret_key="test-key", fingerprint_iterations=1)


@pytest.mark.parametrize(("raw", "canonical"), [
    ("０１０-１２Ｏ４-５６７８", "010-1204-5678"),
    ("０１０-１２O４-５６７８", "010-1204-5678"),
    ("０ １ ０ １ ２ ３ ４ ５ ６ ７ ８", "01012345678"),
    ("０１０-１２\u200bＯ４-５６７８", "010-1204-5678"),
    ("010-1234-567⁸", "010-1234-5678"),
    ("٠١٠-١٢O٤-٥٦٧٨", "010-1204-5678"),
])
def test_composed_normalization_preserves_original_offsets(raw, canonical):
    prefix, suffix = "접수 ﬁ😀: ", " [끝]"
    text = prefix + raw + suffix
    normalized, _ = normalize_unicode(raw)
    assert normalized == canonical
    assert normalize_unicode(normalized)[0] == normalized
    found = detect_all(text, include=["PHONE"])
    assert len(found) == 1
    assert (found[0].start, found[0].end, found[0].text) == (len(prefix), len(prefix) + len(raw), raw)
    result = Anonymizer(strategy="redact", include=["PHONE"]).process(text)
    assert result.text == prefix + "[전화번호]" + suffix
    assert (result.substitutions[0].start, result.substitutions[0].end) == (len(prefix), len(prefix) + len(raw))


@pytest.mark.parametrize(("raw", "expected"), [
    ("ｍｏｄｅｌ０１０-１２Ｏ４-５６７８", "model010-12O4-5678"),
    ("MODEL\u200b-010-12O4-5678", "MODEL-010-12O4-5678"),
    ("０１０-１２Ｏ４-５６７８ｃｏｄｅ", "010-12O4-5678code"),
])
def test_composition_keeps_whole_identifier_boundary(raw, expected):
    assert normalize_unicode(raw)[0] == expected
    assert detect_all(raw, include=["PHONE"]) == []


@pytest.mark.parametrize("entry", ["anonymizer", "standalone", "value", "records"])
@pytest.mark.parametrize(("label", "text"), [
    ("EMAIL", "hong [at] example [dot] com"),
    ("EMAIL", "user＠example.com"),
    ("PHONE", "010-1234-567⁸"),
    ("PHONE", "⁰¹⁰-¹²³⁴-⁵⁶⁷⁸"),
    ("PHONE", "０１０-１２Ｏ４-５６７８"),
    ("CARD", "4111-1111-1111-111¹"),
    ("PASSPORT", "Ｍ１２３４５６７８"),
])
def test_fpe_normalizes_or_masks_across_all_entry_points(entry, label, text):
    vault = _vault()
    if entry == "anonymizer":
        result = Anonymizer(strategy="fpe", include=[label], vault=vault).process(text)
        assert len(result.blocked_items()) == 1
        output = result.text
        assert result.detections[0].token == output
        assert result.detections[0].detection.text == text
    elif entry == "standalone":
        output, returned = fpe(text, detect_all(text, include=[label]), vault=vault)
        assert returned is vault
    elif entry == "value":
        output, returned = anonymize_value(text, label, strategy="fpe", vault=vault)
        assert returned is vault
    else:
        rows, returned = anonymize_records(
            [{"field": text}], column_map={"field": label}, strategy="fpe", vault=vault,
        )
        assert returned is vault
        output = rows[0]["field"]
    assert output != text and output
    if "[at]" in text:
        assert output == "*" * len(text)
    if label == "PHONE":
        assert re.fullmatch(r"010-[0-9]{4}-[0-9]{4}", output)
    assert len(vault) == 1
    stored = vault.entries()[0]
    assert stored.original == text and stored.extra["fpe_value"] == output


def test_email_domain_is_not_numeric_homoglyph_folded():
    result, _ = anonymize_value("user＠BOB12.example", "EMAIL", strategy="fpe", vault=_vault())
    assert result.endswith("@BOB12.example")
    assert not result.startswith("user@")


@pytest.mark.parametrize(("label", "text"), [
    ("EMAIL", "not-an-email"), ("PASSPORT", "not-a-passport"), ("PERSON", "張三"),
])
def test_unsupported_fpe_formats_mask_instead_of_returning_original(label, text):
    out, _ = anonymize_value(text, label, strategy="fpe", vault=_vault())
    assert out == "*" * len(text)


def test_normalization_alone_does_not_count_as_pseudonymization(monkeypatch):
    monkeypatch.setitem(_FPE_BY_LABEL, "PHONE", lambda value, fp: value)
    text = "０１０-１２３４-５６７８"
    assert _pseudonymize_value("PHONE", text, "1" * 64) == "*" * len(text)


@pytest.mark.parametrize(("label", "text"), [
    ("PHONE", "010-1234-5678"), ("RRN", "880101-1234568"),
    ("CARD", "4111-1111-1111-1111"), ("EMAIL", "user@example.com"),
    ("PASSPORT", "M12345678"),
])
def test_regular_fpe_mapping_is_unchanged(label, text):
    vault = _vault()
    fp = vault.fingerprint(label, text)
    assert _pseudonymize_value(label, text, fp) == _FPE_BY_LABEL[label](text, fp)


@pytest.mark.parametrize(("label", "text", "expected"), [
    ("PHONE", "010-1234-567⁸", "010-****-5678"),
    ("PHONE", "０１０-１２Ｏ４-５６７８", "010-****-5678"),
    ("CARD", "4111-1111-1111-111¹", "4111-****-****-1111"),
])
def test_partial_normalization_is_shared_by_all_entry_points(label, text, expected):
    assert mask_value(label, text) == expected
    assert partial(text, detect_all(text, include=[label])) == expected
    assert Anonymizer(strategy="partial", include=[label]).process(text).text == expected
    assert anonymize_value(text, label, strategy="partial")[0] == expected


@pytest.mark.parametrize("label", ["ACCOUNT", "CARD"])
@pytest.mark.parametrize("value", ["1234567", "12345678", "1234-5678"])
def test_short_typed_values_do_not_expose_every_digit(label, value):
    assert mask_value(label, value) == "*" * len(value)
    out, _ = anonymize_records([{"field": value}], column_map={"field": label}, strategy="partial")
    assert out[0]["field"] == "*" * len(value)


def test_partial_retention_policies_are_not_globally_disabled():
    assert mask_value("ACCOUNT", "1234567890") == "1234**7890"
    assert mask_value("CARD", "1234567890123456") == "1234********3456"
    assert mask_value("DT_BIRTH", "88년생") == "88년생"
    assert mask_value("POSITION", "사무관") == "사무관"
