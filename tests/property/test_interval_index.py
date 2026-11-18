"""Independent scan oracles for detector overlap and endpoint-distance queries."""
from hypothesis import given, settings, strategies as st

from ko_pii.core._interval_index import ForwardIntervalIndex
from ko_pii.patterns.person import _is_within


SPANS = st.lists(st.tuples(st.integers(0, 1000), st.integers(1, 1000))
                 .map(lambda pair: (pair[0], pair[0] + pair[1])), max_size=100)


@settings(max_examples=250, deadline=None, derandomize=True)
@given(initial=SPANS,
       queries=st.lists(st.tuples(st.integers(0, 2000), st.integers(1, 100),
                                 st.integers(0, 50), st.booleans(), st.integers(0, 100)), max_size=100))
def test_nested_snapshot_and_forward_additions_match_naive_overlap_scan(initial, queries):
    seen = list(initial)
    index = ForwardIntervalIndex(initial)
    for start, length, margin, accept, extension in sorted(queries):
        end = start + length
        expected = any(start < old_end + margin and old_start - margin < end
                       for old_start, old_end in seen)
        assert index.overlaps(start, end, margin=margin) == expected
        if accept:
            seen.append((start, end + extension))
            index.add(start, end + extension)


@settings(max_examples=250, deadline=None, derandomize=True)
@given(spans=SPANS, position=st.integers(0, 2000), window=st.integers(0, 50))
def test_sorted_endpoint_queries_preserve_endpoint_not_interval_distance(spans, position, window):
    endpoints = sorted(point for span in spans for point in span)
    expected = any(abs(start - position) <= window or abs(end - position) <= window
                   for start, end in spans)
    assert _is_within(spans, position, window, endpoints=endpoints) == expected


def test_interval_interior_does_not_count_as_a_nearby_endpoint():
    assert not _is_within([(0, 1000)], 500, 25, endpoints=[0, 1000])
