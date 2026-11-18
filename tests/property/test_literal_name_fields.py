"""Independent brute-force oracles and raw-range invariants for literal names."""
import unicodedata

from hypothesis import given, settings, strategies as st

from ko_pii import Anonymizer
from ko_pii.context.literal_name_fields import COPULA_ENDINGS, literal_name_mentions
from ko_pii.context.particles import PARTICLES


def word(char):
    return char.isalnum() or char == "_" or unicodedata.category(char).startswith("M")


@settings(max_examples=200, deadline=None, derandomize=True)
@given(names=st.sets(st.sampled_from(["Ann", "Ann Lee", "Lee Park", "John", "John Smith", "金民秀", "장피에르뒤퐁"]), min_size=1),
       pieces=st.lists(st.sampled_from(["Ann Lee Park", "XJohn Smith", "John Smith", "金民秀에게", "金民秀\u0301", "John_", "장피에르뒤퐁입니다", "(Ann)", "\n", " "]), max_size=20))
def test_alias_index_matches_brute_force_longest_valid_value_at_each_start(names, pieces):
    text = " ".join(pieces)
    expected = []
    endings = sorted(set(PARTICLES) | set(COPULA_ENDINGS), key=lambda value: (-len(value), value))
    for start in range(len(text)):
        if start and word(text[start - 1]):
            continue
        candidates = []
        for name in names:
            if not text.startswith(name, start):
                continue
            end = start + len(name)
            if end == len(text) or not word(text[end]):
                candidates.append((start, end, None))
            else:
                suffix = next((value for value in endings if text.startswith(value, end)), None)
                if suffix is not None:
                    after = end + len(suffix)
                    if after == len(text) or not word(text[after]):
                        candidates.append((start, end, suffix))
        if candidates:
            expected.append(max(candidates, key=lambda value: value[1]))
    assert list(literal_name_mentions(text, names)) == expected


@settings(max_examples=200, deadline=None, derandomize=True)
@given(name=st.sampled_from(["장피에르뒤퐁", "김마리아은", "John Smith", "Anne-Marie O'Neill", "José Álvarez", "金民秀", "김 민수"]),
       prefix=st.sampled_from(["성명: ", "**성함**: ", "성명(영문): ", "| 성명 | "]),
       wrapper=st.sampled_from([("", ""), ('"', '"'), ("**", "**"), ("__", "__"), ("`", "`")]),
       form=st.sampled_from(["NFC", "NFD"]))
def test_extended_field_preserves_original_range_and_all_outside_characters(name, prefix, wrapper, form):
    prefix = unicodedata.normalize(form, prefix) + wrapper[0]
    raw = unicodedata.normalize(form, name)
    suffix = wrapper[1] + " | public"
    source = prefix + raw + suffix
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == prefix + "[성명]" + suffix
    assert [(item.detection.start, item.detection.end, item.detection.text) for item in result.detections] == [
        (len(prefix), len(prefix) + len(raw), raw),
    ]
