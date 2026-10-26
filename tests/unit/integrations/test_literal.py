import pytest

from ko_pii import Anonymizer, LiteralDetector, ProcessingMode


@pytest.mark.parametrize("boundary,expected", [
    ("word", ["김도구"]), ("korean", ["김도구", "김도구", "김도구"]),
    ("substring", ["김도구"] * 6),
])
def test_boundaries_and_original_offsets(boundary, expected):
    text = "김도구 김도구에게 김도구에게서 김도구리 큰김도구 김도구에게서는"
    found = list(LiteralDetector({"PERSON": ["김도구"]}, boundary=boundary).detect(text))
    assert [r.text for r in found] == expected
    assert all(text[r.start:r.end] == r.text for r in found)


def test_literal_escapes_and_longest_valid_value():
    detector = LiteralDetector({"PERSON": ["A+B", "A+B", "A+B Co", "A"]})
    assert [r.text for r in detector.detect("A+B! A+B Company A+B Co")] == ["A+B", "A+B", "A+B Co"]


def test_overlapping_starts_and_no_normalization():
    detector = LiteralDetector({"PERSON": ["aba"]}, boundary="substring")
    assert [(r.start, r.end) for r in detector.detect("ababa")] == [(0, 3), (2, 5)]
    assert not list(detector.detect("ABA ａｂａ a\u200bba"))


@pytest.mark.parametrize("label,term", [("EMAIL", "김도구"), ("PERSON", "Alice")])
def test_korean_suffix_is_limited_to_hangul_person(label, term):
    assert not list(LiteralDetector({label: [term]}, boundary="korean").detect(term + "에게"))


@pytest.mark.parametrize("values", [
    {}, {"UNKNOWN": ["secret"]}, {"PERSON": "secret"}, {"PERSON": []},
    {"PERSON": [""]}, {"PERSON": ["  "]}, {"PERSON": [None]},
    {"PERSON": ["x" * 257]}, {"PERSON": ["secret"] * 1025},
    {"PERSON": ["a" * 256] * 257}, {"PERSON": ["secret"], "EMAIL": ["secret"]},
])
def test_invalid_config_is_sanitized(values):
    with pytest.raises(ValueError) as exc:
        LiteralDetector(values)
    assert "secret" not in str(exc.value)


def test_failing_generator_is_sanitized():
    def bad():
        yield "Alice"
        raise RuntimeError("private value")
    with pytest.raises(ValueError, match="invalid or beyond-limit"):
        LiteralDetector({"PERSON": bad()})


@pytest.mark.parametrize("boundary", [None, [], "fuzzy"])
def test_invalid_boundary(boundary):
    with pytest.raises(ValueError):
        LiteralDetector({"PERSON": ["Alice"]}, boundary=boundary)


def test_caps_fail_before_yield():
    detector = LiteralDetector({"PERSON": ["Alice"]}, max_matches=1)
    with pytest.raises(ValueError):
        next(detector.detect("Alice Alice"))
    with pytest.raises(ValueError):
        list(LiteralDetector({"PERSON": ["Alice"]}, max_chars=2).detect("Alice"))


def test_anonymizer_integration_and_exclusions():
    detector = LiteralDetector({"PERSON": ["김도구"]}, boundary="korean")
    anon = Anonymizer(mode=ProcessingMode.STRICT, secondary_detector=detector, include=["PERSON"])
    assert anon.process("김도구에게").text == "<PERSON_1>에게"
    excluded = Anonymizer(secondary_detector=detector, exclude=["PERSON"])
    assert excluded.process("김도구에게").text == "김도구에게"
    domain = Anonymizer(secondary_detector=detector, person_exclusions=["김도구"])
    assert domain.process("김도구에게").text == "김도구에게"
