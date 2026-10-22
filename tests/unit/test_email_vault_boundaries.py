"""Boundary regressions for prose preservation and persisted token identity."""
import copy
import json
import random

import pytest

from ko_pii import Anonymizer, detect_all
from ko_pii.modes.tokenize import tokenize
from ko_pii.patterns.email import detect
from ko_pii.vault.reversible import ReversibleVault


@pytest.mark.parametrize("prefix", [
    "Please email ", "Contact support at: ", "README\nContact\n", "Header\r\n",
    "Header\r", "Header\v", "Header\f", "Header\u0085", "Header\u2028",
    "Header\u2029", "Contact\t", "문의: ", "Header\x1c",
])
@pytest.mark.parametrize("email", ["john [at] example [dot] com", "john\t(AT)\texample\t(DOT)\tcom"])
def test_obfuscated_email_preserves_surrounding_text(prefix, email):
    text = prefix + email + " [end]"
    result = Anonymizer(strategy="redact", include=["EMAIL"]).process(text)
    assert result.text == prefix + "[이메일] [end]"
    detection = result.detections[0].detection
    assert (detection.start, detection.end) == (len(prefix), len(prefix) + len(email))
    assert detection.text == text[detection.start:detection.end] == email
    assert detection.extra["value"] == "john@example.com"


def test_multiple_email_records_keep_prose_and_offsets():
    text = "Ask first@example.com or contact second [at] example [dot] org."
    result = Anonymizer(strategy="tokenize", include=["EMAIL"]).process(text)
    assert result.text == "Ask <EMAIL_1> or contact <EMAIL_2>."
    assert result.vault.reveal("<EMAIL_1>") == "first@example.com"
    assert result.vault.reveal("<EMAIL_2>") == "second [at] example [dot] org"


def test_normalized_obfuscated_email_preserves_prose():
    text = "Contact ｊｏｈｎ [at] example [dot] com."
    result = Anonymizer(strategy="redact", include=["EMAIL"]).process(text)
    assert result.text == "Contact [이메일]."
    assert result.detections[0].detection.text == "ｊｏｈｎ [at] example [dot] com"


def test_email_line_boundary_handling_preserves_numeric_evasion_detection():
    text = "Header\x85ｊｏｈｎ [at] example [dot] com, phone 010-12\x8534-5678"
    result = Anonymizer(strategy="redact", include=["EMAIL", "PHONE"]).process(text)
    assert result.text == "Header\x85[이메일], phone [전화번호]"
    for record in result.detections:
        d = record.detection
        assert d.text == text[d.start:d.end]


def test_email_source_text_survives_length_preserving_normalization():
    text = "Header\x85BO12 [at] example [dot] com"
    for d in detect_all(text, include=["EMAIL"]):
        assert d.text == text[d.start:d.end]


def test_spaced_local_requires_explicit_low_level_opt_in():
    text = "hong gildong @ naver . com"
    assert list(detect(text))[0].text == "gildong @ naver . com"
    assert detect_all(text, include=["EMAIL"])[0].text == "gildong @ naver . com"
    assert Anonymizer(strategy="redact", include=["EMAIL"]).process(text).text == "hong [이메일]"
    output, vault = tokenize(text, detect(text, allow_spaced_local=True))
    assert output == "<EMAIL_1>"
    assert vault.reveal("<EMAIL_1>") == text
    spaced = list(detect("hong\tgildong @ naver . com", allow_spaced_local=True))
    assert spaced[0].extra["value"] == "honggildong@naver.com"


@pytest.mark.parametrize("opt_in", [False, True])
@pytest.mark.parametrize("separator", ["\n", "\r\n", "\u2028", "\v"])
def test_email_never_joins_across_line_boundaries(opt_in, separator):
    text = "Header" + separator + "john [at] example [dot] com"
    assert list(detect(text, allow_spaced_local=opt_in))[0].text == "john [at] example [dot] com"
    for text in ["john" + separator + "[at] example [dot] com",
                 "john [at]" + separator + "example [dot] com",
                 "john [at] example [dot]" + separator + "com"]:
        assert list(detect(text, allow_spaced_local=opt_in)) == []


def _payload():
    vault = ReversibleVault(salt="test")
    vault.store("PHONE", "018-2345-6789", 3)
    return vault.to_dict()


def test_loaded_label_token_mismatch_is_rejected_without_changing_payload():
    payload = _payload()
    payload["entries"]["<PHONE_1>"]["label"] = "EMAIL"
    before = copy.deepcopy(payload)
    with pytest.raises(ValueError, match="token does not match"):
        ReversibleVault.from_dict(payload)
    assert payload == before


@pytest.mark.parametrize("token", ["<PHONE_0>", "<PHONE_-1>", "<PHONE_01>",
                                  "<PHONE_1", "PHONE_1>", "<PHONE_١>", "<PHONE_1>>", 1])
def test_malformed_tokens_are_rejected(token):
    payload = _payload()
    payload["entries"][token] = payload["entries"].pop("<PHONE_1>")
    with pytest.raises(ValueError):
        ReversibleVault.from_dict(payload)


@pytest.mark.parametrize("field,value", [
    ("label", None), ("label", []), ("original", 1), ("original", []),
    ("risk_level", True), ("risk_level", 0), ("risk_level", 6), ("risk_level", "3"),
    ("legal_basis", []), ("first_seen_offset", -2), ("first_seen_offset", True),
    ("occurrences", "12"), ("occurrences", [-1]), ("occurrences", [True]),
    ("extra", []),
])
def test_invalid_entry_fields_are_rejected(field, value):
    payload = _payload()
    payload["entries"]["<PHONE_1>"][field] = value
    with pytest.raises(ValueError):
        ReversibleVault.from_dict(payload)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("salt", None), ("created_at", []), ("entries", []),
    ("fingerprint_scheme", "unsupported"), ("fingerprint_scheme", []),
    ("fingerprint_iterations", 0), ("fingerprint_iterations", -1),
    ("fingerprint_iterations", True), ("fingerprint_iterations", "1000"),
    ("fingerprint_iterations", 1.5),
])
def test_invalid_vault_fields_are_rejected(field, value):
    payload = _payload()
    payload[field] = value
    with pytest.raises(ValueError):
        ReversibleVault.from_dict(payload)


@pytest.mark.parametrize("payload", [None, [], "secret-text", 1])
def test_non_object_vault_is_rejected(payload):
    with pytest.raises(ValueError):
        ReversibleVault.from_dict(payload)


def test_duplicate_identities_cannot_have_two_tokens():
    payload = _payload()
    payload["entries"]["<PHONE_2>"] = copy.deepcopy(payload["entries"]["<PHONE_1>"])
    with pytest.raises(ValueError, match="Duplicate vault identity"):
        ReversibleVault.from_dict(payload)


def test_json_duplicate_keys_rejected_at_every_level_without_echoing_values():
    for raw in [
        '{"schema_version":1,"salt":"x","entries":{},"entries":{}}',
        '{"schema_version":1,"salt":"x","entries":{"private-key":{},"private-key":{}}}',
        '{"schema_version":1,"salt":"x","extra":{"private-key":1,"private-key":2}}',
    ]:
        with pytest.raises(ValueError, match="duplicate") as error:
            ReversibleVault.loads(raw)
        assert "private-key" not in str(error.value)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_is_rejected(constant):
    with pytest.raises(ValueError, match="non-finite"):
        ReversibleVault.loads('{"schema_version":1,"salt":"x","extra":' + constant + '}')


def test_store_guard_detects_mutated_entry_without_changing_state():
    vault = ReversibleVault.from_dict(_payload())
    vault.get("<PHONE_1>").original = "other value"
    before = copy.deepcopy(vault.to_dict())
    with pytest.raises(ValueError, match="Inconsistent"):
        vault.store("PHONE", "018-2345-6789", 3, offset=100)
    assert vault.to_dict() == before


def test_store_guard_checks_collision_before_reserving_token():
    vault = ReversibleVault.from_dict(_payload())
    vault._counters["PHONE"] = 0
    before = copy.deepcopy(vault.to_dict())
    reverse = dict(vault._reverse)
    with pytest.raises(ValueError, match="Conflicting"):
        vault.store("PHONE", "010-9876-5432", 3)
    assert vault.to_dict() == before
    assert vault._reverse == reverse
    assert vault._counters["PHONE"] == 0


def test_valid_legacy_and_current_vaults_preserve_generated_roundtrips():
    rng = random.Random(20261022)
    for _ in range(100):
        vault = ReversibleVault(salt="test")
        pairs = [(rng.choice(["PHONE", "EMAIL", "CUSTOM_LABEL"]), str(rng.randrange(100)))
                 for _ in range(30)]
        tokens = [vault.store(label, value, 3, offset=i) for i, (label, value) in enumerate(pairs)]
        for legacy in (False, True):
            payload = vault.to_dict()
            if legacy:
                payload.pop("fingerprint_scheme")
                payload.pop("fingerprint_iterations")
            loaded = ReversibleVault.loads(json.dumps(payload))
            for (label, value), token in zip(pairs, tokens):
                assert loaded.store(label, value, 3) == token
                assert loaded.reveal(token) == value
            new = loaded.store("PHONE", "new-value", 3)
            assert new not in tokens
            assert loaded.reveal(new) == "new-value"


def test_rejected_file_remains_unchanged(tmp_path):
    payload = _payload()
    payload["entries"]["<PHONE_1>"]["label"] = "EMAIL"
    path = tmp_path / "vault.json"
    original = json.dumps(payload)
    path.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        ReversibleVault.load(str(path))
    assert path.read_text(encoding="utf-8") == original


def test_encrypted_load_also_rejects_inconsistent_mapping(tmp_path):
    pytest.importorskip("cryptography")
    from ko_pii.vault.encrypted import load_encrypted, save_encrypted

    vault = ReversibleVault.from_dict(_payload())
    vault.get("<PHONE_1>").label = "EMAIL"
    path = tmp_path / "broken.kvault"
    save_encrypted(vault, str(path), "test-only-password")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="token does not match"):
        load_encrypted(str(path), "test-only-password")
    assert path.read_bytes() == before


@pytest.mark.parametrize("iterations", [0, -1, True, "1000", 1.5])
def test_constructor_rejects_invalid_fingerprint_iterations(iterations):
    with pytest.raises(ValueError, match="fingerprint_iterations"):
        ReversibleVault(fingerprint_iterations=iterations)
