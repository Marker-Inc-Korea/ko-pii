"""Public transformation primitives must bind each result to its source."""
from dataclasses import replace
import math

import pytest

from ko_pii import (
    DetectionResult, RiskLevel, ReversibleVault, fpe, hashed, partial, redact, tokenize,
)


SOURCE = "alice@example.com bob@example.com"
VALUE = "alice@example.com"
MODES = [tokenize, redact, hashed, partial, fpe]
VAULT_MODES = [tokenize, hashed, fpe]


def record():
    return DetectionResult("EMAIL", VALUE, 0, len(VALUE), RiskLevel.MEDIUM)


def invoke(mode, text, detections, vault=None):
    result = mode(text, detections, vault=vault) if mode in VAULT_MODES else mode(text, detections)
    return result[0] if isinstance(result, tuple) else result


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("changes", [
    {"end": 0, "text": ""}, {"start": -1}, {"end": len(SOURCE) + 1},
    {"start": 20, "end": 19}, {"start": False}, {"end": 17.0},
    {"text": "other@example.com"}, {"text": None},
    {"risk_level": 3}, {"confidence": math.nan}, {"confidence": 2},
    {"label": ""}, {"label": "<EMAIL>"}, {"extra": []},
])
def test_invalid_source_result_is_rejected_before_vault_write(mode, changes):
    vault = ReversibleVault(salt="synthetic-boundary-test")
    valid = record()
    invalid = replace(record(), **changes)
    with pytest.raises(ValueError) as caught:
        invoke(mode, SOURCE, [valid, invalid], vault)
    assert VALUE not in str(caught.value) and "other@example.com" not in str(caught.value)
    assert len(vault) == 0


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("value", [None, b"private", 0])
def test_non_text_source_fails_even_without_detections(mode, value):
    with pytest.raises(ValueError):
        invoke(mode, value, [])


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("invalid", [None, {}, "alice@example.com"])
def test_non_detection_record_is_rejected(mode, invalid):
    with pytest.raises(ValueError):
        invoke(mode, SOURCE, [invalid])


@pytest.mark.parametrize("mode", MODES)
def test_reused_generator_record_is_snapshotted_before_next_yield(mode):
    def detections():
        item = record()
        yield item
        item.start, item.end, item.text = 18, len(SOURCE), "bob@example.com"
        yield item
        item.start, item.end, item.text = 0, 0, ""

    vault = ReversibleVault(salt="synthetic-snapshot-test")
    output = invoke(mode, SOURCE, detections(), vault)
    assert VALUE not in output and "bob@example.com" not in output
    if mode is tokenize:
        assert output == "<EMAIL_1> <EMAIL_2>"
    if mode in [tokenize, fpe]:
        assert vault.reveal("<EMAIL_1>") == VALUE
        assert vault.reveal("<EMAIL_2>") == "bob@example.com"


@pytest.mark.parametrize("mode", MODES)
def test_late_iterator_failure_does_not_leak_input_or_write_vault(mode):
    def detections():
        yield record()
        raise RuntimeError("private input " + SOURCE)

    vault = ReversibleVault(salt="synthetic-iterator-test")
    with pytest.raises(ValueError) as caught:
        invoke(mode, SOURCE, detections(), vault)
    assert VALUE not in str(caught.value)
    assert caught.value.__suppress_context__
    assert len(vault) == 0


@pytest.mark.parametrize("mode", VAULT_MODES)
def test_preflight_rejects_before_store_or_fingerprint(mode, monkeypatch):
    vault = ReversibleVault(salt="synthetic-no-side-effects")

    def forbidden(*args, **kwargs):
        raise AssertionError("Vault operation must not precede input validation")

    monkeypatch.setattr(vault, "store", forbidden)
    monkeypatch.setattr(vault, "fingerprint", forbidden)
    with pytest.raises(ValueError):
        invoke(mode, SOURCE, [record(), replace(record(), text="wrong")], vault)


@pytest.mark.parametrize("mode", MODES)
def test_custom_label_and_valid_empty_input_keep_compatibility(mode):
    item = DetectionResult("INTERNAL_ID", "abc123", 0, 6, RiskLevel.HIGH)
    output = invoke(mode, "abc123", [item])
    assert output != "abc123"
    assert invoke(mode, "", []) == ""
    assert invoke(mode, "public", []) == "public"


@pytest.mark.parametrize("mode", MODES)
def test_valid_overlaps_and_order_match_detached_list(mode):
    first, second = record(), DetectionResult("EMAIL", "bob@example.com", 18, len(SOURCE), RiskLevel.MEDIUM)
    low = DetectionResult("URL", SOURCE, 0, len(SOURCE), RiskLevel.LOW)
    rows = [second, low, first, replace(first)]
    left = invoke(mode, SOURCE, rows, ReversibleVault(salt="stable"))
    right = invoke(mode, SOURCE, iter([first, second]), ReversibleVault(salt="stable"))
    assert left == right


@pytest.mark.parametrize("length", [0, -1, 65, True, 1.5, "12", None])
def test_digest_length_rejects_silent_truncation_and_empty_identifiers(length):
    with pytest.raises(ValueError):
        hashed(SOURCE, [record()], digest_len=length)
    with pytest.raises(ValueError):
        hashed("", [], digest_len=length)


@pytest.mark.parametrize("length", [1, 8, 12, 64])
def test_supported_digest_lengths_preserve_requested_shape(length):
    output, _ = hashed(VALUE, [record()], vault=ReversibleVault(salt="stable"), digest_len=length)
    digest = output.removeprefix("<EMAIL:").removesuffix(">")
    assert len(digest) == length
    assert set(digest) <= set("0123456789abcdef")
