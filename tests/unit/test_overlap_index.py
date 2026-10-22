"""Compare indexed overlap selection with the original pairwise semantics."""
import random

import pytest

from ko_pii import Anonymizer
from ko_pii.core.overlap import _select_non_overlapping, resolve_overlaps
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.patterns import email, phone


def _naive(items):
    accepted = []
    for d in items:
        if not any(d.start < a.end and a.start < d.end for a in accepted):
            accepted.append(d)
    return accepted


def _ids(items):
    return [id(d) for d in items]


def test_index_matches_pairwise_oracle_with_priority_ties_and_arbitrary_spans():
    rng = random.Random(20261022)
    for _ in range(300):
        items = [DetectionResult(
            label="PHONE", text=str(i), start=rng.randrange(-10, 80), end=rng.randrange(-10, 80),
            risk_level=rng.choice(list(RiskLevel)), confidence=rng.choice([0.7, 0.9, 1.0]),
        ) for i in range(rng.randrange(100))]
        assert _ids(_select_non_overlapping(items)) == _ids(_naive(items))
        ordered = sorted(items, key=lambda d: (-int(d.risk_level), -d.confidence, -(d.end - d.start), d.start))
        expected = sorted(_naive(ordered), key=lambda d: (d.start, d.end))
        assert _ids(resolve_overlaps(iter(items))) == _ids(expected)


def test_adjacent_and_equal_priority_spans_preserve_order_and_identity():
    items = [DetectionResult("PHONE", "", s, e, RiskLevel.HIGH) for s, e in
             [(4, 8), (0, 4), (0, 4), (8, 12), (3, 5), (4, 4)]]
    assert _ids(_select_non_overlapping(items)) == _ids(_naive(items))
    assert _ids(resolve_overlaps(items)) == _ids([items[1], items[5], items[0], items[3]])


def test_phone_pattern_priority_and_metadata_match_original_algorithm():
    text = " | ".join([
        "+82 (0)10-1234-5678", "(031) 123-4567", "010-1234-5678", "+82-2-1234-5678",
        "02) 1234-5678", "+82-70-1234-5678", "070-1234-5678", "1588-1234",
        "(010) 9876-5432", "(070) 1234-5678", "+82-31-123-4567", "031-123-4567",
    ] * 20)
    candidates = []
    for pattern, kind, international in (
        (phone._PAREN_AREA, None, False), (phone._MOBILE_INTL, "mobile", True),
        (phone._SEOUL_INTL, "landline", True), (phone._REGIONAL_INTL, None, True),
        (phone._MOBILE, "mobile", False), (phone._REGIONAL, None, False),
        (phone._SEOUL, "landline", False), (phone._REPRESENTATIVE, "representative", False),
    ):
        for m in pattern.finditer(text):
            subtype = kind
            if subtype is None:
                prefix = m.group(1)
                subtype = ("mobile" if prefix.startswith("01") else
                           "voip" if prefix in {"070", "70"} else "landline")
            candidates.append(phone._emit(m, subtype, international))
    assert list(phone.detect(text)) == _naive(candidates)


def test_anchored_email_matching_preserves_regex_matches():
    rng = random.Random(19)
    parts = ["a", "abc", "010-1234-5678", " ", "\n", "\t", "\u00a0", "@", "[at]", "(AT)",
             "[ at ]", ".", "[dot]", "( dot )", "gov.kr", "user", "!", "한글", "İ", "ſ", "K"]
    samples = [
        "a@b user [at] example [dot] com", "user @ example . com next [at] gov [dot] kr",
        "a@b@c d [at] host [dot] com", ".bad user [at] example [dot] com",
    ] + ["".join(rng.choices(parts, k=50)) for _ in range(500)]
    for text in samples:
        expected = [(m.span(), m.group()) for m in email._OBFUSCATED.finditer(text)]
        actual = [(m.span(), m.group()) for m in email._obfuscated_matches(text)]
        assert actual == expected, repr(text)


@pytest.mark.parametrize("strategy", ["tokenize", "hashed", "partial", "fpe"])
def test_many_replacements_keep_record_tokens_and_source_offsets(strategy):
    text = "010-1234-5678\n" * 300
    result = Anonymizer(strategy=strategy, include=["PHONE"]).process(text)
    assert len(result.detections) == len(result.substitutions) == 300
    for record in result.detections:
        assert record.token and record.token in result.text
        assert text[record.detection.start:record.detection.end] == record.detection.text
    if strategy in {"tokenize", "fpe"}:
        assert len(result.vault) == 1
        assert result.vault.entries()[0].occurrences == list(range(0, len(text), len("010-1234-5678\n")))
