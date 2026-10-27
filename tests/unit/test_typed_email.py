"""Typed fields must not treat trailing prose or addresses as a domain."""
import pytest

from ko_pii import Anonymizer
from ko_pii.modes.fpe import fpe
from ko_pii.modes.partial import mask_value, partial
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.structured import anonymize_json
from ko_pii.tabular import anonymize_records, anonymize_value
from ko_pii.vault.reversible import ReversibleVault


def _transform(text, strategy, entry):
    vault = ReversibleVault(salt="test", secret_key="test", fingerprint_iterations=1)
    if entry == "records":
        return anonymize_records([{"email": text}], strategy=strategy, vault=vault)[0][0]["email"]
    if entry == "json":
        return anonymize_json(
            {"email": text}, field_labels={"/email": "EMAIL"},
            anonymizer=Anonymizer(strategy=strategy, vault=vault),
        ).data["email"]
    if entry == "span":
        detections = [DetectionResult("EMAIL", text, 0, len(text), RiskLevel.MEDIUM, 1.0)]
        return partial(text, detections) if strategy == "partial" else fpe(text, detections, vault)[0]
    return anonymize_value(text, "EMAIL", strategy=strategy, vault=vault)[0]


@pytest.mark.parametrize("strategy", ["partial", "fpe"])
@pytest.mark.parametrize("entry", ["records", "json", "value", "span"])
@pytest.mark.parametrize("text", [
    "first@example.com;second@example.com",
    "first@example.com, second@example.com",
    "first@example.com\nsecond@example.com",
    "first@example.com\tsecond@example.com",
    "first@example.com (private-name)",
    "first@example.com/010-1234-5678",
    "Name <first@example.com>",
    "@example.com;second@example.com",
    "first@example.com second [at] example [dot] com",
    "first@@example.com",
])
def test_compound_or_unsupported_email_fields_are_fully_masked(strategy, entry, text):
    assert _transform(text, strategy, entry) == "*" * len(text)


@pytest.mark.parametrize("strategy", ["partial", "fpe"])
@pytest.mark.parametrize("text", ["user@example.com", "user+tag@example.com", "user@xn--3e0b707e.com",
                                  "user@한국.com", "a@b.c"])
def test_supported_single_email_keeps_only_its_domain(strategy, text):
    output = _transform(text, strategy, "value")
    assert output != text
    assert output.endswith("@" + text.partition("@")[2])


@pytest.mark.parametrize("strategy", ["partial", "fpe", "tokenize"])
def test_plain_text_multiple_emails_remain_independently_transformed(strategy):
    text = "Ask first@example.com or second@example.com."
    output = Anonymizer(strategy=strategy, include=["EMAIL"]).process(text).text
    assert output.startswith("Ask ") and " or " in output and output.endswith(".")
    assert "first@example.com" not in output and "second@example.com" not in output


@pytest.mark.parametrize("text", ["@example.com", ".user@example.com", "user..name@example.com",
                                  "user@example..com", "user@-example.com", "user@example.com\n"])
def test_direct_partial_helper_rejects_malformed_email(text):
    assert mask_value("EMAIL", text) == "*" * len(text)
