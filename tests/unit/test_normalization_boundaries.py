"""Canonical Hangul boundaries must survive source-coordinate remapping."""
import json
import unicodedata as ud

import pytest

from ko_pii import Anonymizer, PreForwardAnonymizer, ProcessingMode, anonymize_json
from ko_pii.cli import main
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.core.unicode_norm import normalize_unicode, remap_to_source


NAME = "\ud64d\uae38\ub3d9"
ADDRESS = "\uc11c\uc6b8\ud2b9\ubcc4\uc2dc \uac15\ub0a8\uad6c \ud14c\ud5e4\ub780\ub85c 152"


@pytest.mark.parametrize("prefix", ["", "\uc131\uba85: ", "\U0001f600 "])
@pytest.mark.parametrize("suffix", ["\uc5d0\uac8c", "\uc758", "\uc740"])
@pytest.mark.parametrize("strategy", ["redact", "tokenize", "asterisk", "partial", "hashed", "fpe"])
def test_decomposed_name_is_replaced_without_consuming_prefix_or_particle(prefix, suffix, strategy):
    source = ud.normalize("NFD", prefix + NAME + suffix)
    result = Anonymizer(include=["PERSON"], strategy=strategy).process(source)
    assert len(result.detections) == 1
    detection = result.detections[0].detection
    begin = len(ud.normalize("NFD", prefix))
    finish = begin + len(ud.normalize("NFD", NAME))
    assert (detection.start, detection.end) == (begin, finish)
    assert detection.text == source[begin:finish] == ud.normalize("NFD", NAME)
    assert NAME not in ud.normalize("NFC", result.text)
    assert result.text.startswith(source[:begin]) and result.text.endswith(source[finish:])
    assert len(result.substitutions) == 1
    replacement = result.substitutions[0]
    assert (replacement.start, replacement.end) == (begin, finish)
    if strategy == "tokenize":
        assert result.vault.reveal("<PERSON_1>") == source[begin:finish]


def test_audit_still_preserves_the_exact_decomposed_source():
    source = ud.normalize("NFD", NAME + "\uc5d0\uac8c")
    result = Anonymizer(mode=ProcessingMode.AUDIT, include=["PERSON"]).process(source)
    assert result.text == source
    assert result.substitutions == []
    assert len(result.detections) == 1
    detection = result.detections[0].detection
    assert (detection.start, detection.end) == (0, len(ud.normalize("NFD", NAME)))


@pytest.mark.parametrize("entry", ["text", "json", "stream"])
def test_address_keeps_final_digit_and_excludes_decomposed_suffix(entry):
    prefix, suffix = "\uc8fc\uc18c\ub294 ", "\uc785\ub2c8\ub2e4"
    source = ud.normalize("NFD", prefix + ADDRESS + suffix)
    anon = Anonymizer(include=["ADDRESS"], strategy="redact")
    if entry == "json":
        result = anonymize_json({"message": source}, anonymizer=anon).fields[0].result
    elif entry == "stream":
        stream = PreForwardAnonymizer(anon)
        for char in source:
            status = stream.feed(char)
            assert not status.closed
        result = stream.finalize()
    else:
        result = anon.process(source)
    begin = len(ud.normalize("NFD", prefix))
    finish = begin + len(ud.normalize("NFD", ADDRESS))
    assert result.text == source[:begin] + "[\uc8fc\uc18c]" + source[finish:]
    d = result.detections[0].detection
    assert (d.start, d.end, d.text) == (begin, finish, source[begin:finish])


def test_every_modern_hangul_syllable_has_its_own_source_range():
    canonical = "".join(chr(cp) for cp in range(0xAC00, 0xD7A4))
    pieces = [ud.normalize("NFD", char) for char in canonical]
    starts = []
    position = 0
    for piece in pieces:
        starts.append(position)
        position += len(piece)
    normalized, offsets = normalize_unicode("".join(pieces), fold_numeric=False)
    assert normalized == canonical
    assert offsets == starts


@pytest.mark.parametrize("prefix", ["", " ", "0", ":", "x", "\U0001f600"])
def test_hangul_never_inherits_position_from_previous_starter(prefix):
    source = prefix + ud.normalize("NFD", "\ud64d\uae38\ub3d9\uc758")
    normalized, offsets = normalize_unicode(source, fold_numeric=False)
    assert normalized == prefix + "\ud64d\uae38\ub3d9\uc758"
    assert offsets == list(range(len(prefix))) + [len(prefix) + x for x in (0, 3, 6, 9)]


@pytest.mark.parametrize("source,expected,offsets", [
    ("\ud558\u11ab\u1100\u1173\u11af", "\ud55c\uae00", [0, 2]),
    ("\u1112\u1161\ub298", "\ud558\ub298", [0, 2]),
    ("\u314e\u314f\u11ab\u3131\u3161\u11af", "\ud55c\uae00", [0, 3]),
    ("\u1100\u0301\u1161", "\u1100\u0301\u1161", [0, 0, 2]),
])
def test_mixed_and_compatibility_jamo_composition_respects_blocking(source, expected, offsets):
    normalized, actual = normalize_unicode(source, fold_numeric=False)
    assert normalized == expected == ud.normalize("NFKC", source)
    assert actual == offsets


@pytest.mark.parametrize("source", ["\ufb03", "\u2469", "\u2167"])
def test_partial_match_inside_nfkc_expansion_covers_the_whole_source_character(source):
    text, offsets = normalize_unicode(source, fold_numeric=False)
    assert len(text) > 1
    for start in range(len(text)):
        for end in range(start + 1, len(text) + 1):
            original = DetectionResult("PERSON", text[start:end], start, end, RiskLevel.HIGH)
            mapped = remap_to_source([original], offsets, source)[0]
            assert (mapped.start, mapped.end, mapped.text) == (0, 1, source)


def test_chunk_boundaries_inside_jamo_do_not_change_the_final_result():
    source = ud.normalize("NFD", "\uc131\uba85: " + NAME + "\uc5d0\uac8c")
    expected = ud.normalize("NFD", "\uc131\uba85: ") + "[\uc131\uba85]" + ud.normalize("NFD", "\uc5d0\uac8c")
    for split in range(len(source) + 1):
        stream = PreForwardAnonymizer(Anonymizer(include=["PERSON"], strategy="redact"))
        stream.feed(source[:split])
        stream.feed(source[split:])
        assert stream.finalize().text == expected


def test_cli_writes_replaced_name_not_an_empty_source_substitution(tmp_path, capsys):
    source, output = tmp_path / "input.txt", tmp_path / "output.txt"
    source.write_text(ud.normalize("NFD", NAME + "\uc5d0\uac8c"), encoding="utf-8")
    assert main([str(source), "--strategy", "redact", "--output", str(output), "--json-summary"]) == 0
    assert output.read_text(encoding="utf-8") == "[\uc131\uba85]" + ud.normalize("NFD", "\uc5d0\uac8c")
    assert json.loads(capsys.readouterr().err)


@pytest.mark.parametrize("source", [
    "1\u110001", "1\u1100\u110001", "1\u030101", "e\u0301", "\u1100",
])
def test_numeric_noise_and_latin_composition_regressions(source):
    expected = {"1\u110001": "101", "1\u1100\u110001": "101", "1\u030101": "101",
                "e\u0301": "\u00e9", "\u1100": "\u1100"}[source]
    assert normalize_unicode(source)[0] == expected
