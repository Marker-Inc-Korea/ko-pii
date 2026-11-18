"""Independent span and connected-number invariants for financial detectors."""
from hypothesis import given, settings, strategies as st

from ko_pii import Anonymizer, detect_all
from ko_pii.patterns.account import _overlaps_previous


@settings(max_examples=300, deadline=None, derandomize=True)
@given(specs=st.lists(st.tuples(st.integers(0, 100), st.integers(1, 40)), max_size=40),
       start=st.integers(0, 130), length=st.integers(1, 40))
def test_previous_pass_overlap_index_matches_an_independent_interval_scan(specs, start, length):
    occupied = []
    for begin, size in sorted(specs):
        end = begin + size
        if occupied and begin <= occupied[-1][1]:
            occupied[-1] = (occupied[-1][0], max(occupied[-1][1], end))
        else:
            occupied.append((begin, end))
    query = (start, start + length)
    assert _overlaps_previous(query, occupied) == any(a < query[1] and query[0] < b for a, b in occupied)


@settings(max_examples=200, deadline=None, derandomize=True)
@given(separator=st.sampled_from(["-", ".", "/", " ", "  ", "- ", "-\n", "-\r\n"]),
       extra=st.text(alphabet="0123456789", min_size=4, max_size=7),
       side=st.sampled_from(["before", "after"]),
       wide=st.booleans())
def test_a_card_checksum_inside_an_overlong_grouped_value_is_not_an_independent_card(separator, extra, side, wide):
    groups = ["4111", "1111", "1111", "1111"]
    groups = [extra, *groups] if side == "before" else [*groups, extra]
    source = separator.join(groups)
    if wide:
        source = "".join(chr(ord(ch) + 0xFEE0) if "0" <= ch <= "9" else ch for ch in source)
    assert detect_all(source, include=["CARD"]) == []
    assert Anonymizer(strategy="redact", include=["CARD"]).process(source).text == source
