"""Independent interval-union oracle for full-mask overlap protection."""
from hypothesis import given, settings, strategies as st

from ko_pii.core._coverage import protection_remainders
from ko_pii.core.modes import Action, policy_for, ProcessingMode
from ko_pii.core.overlap import resolve_overlaps
from ko_pii.core.types import DetectionResult, RiskLevel


@settings(max_examples=300, deadline=None, derandomize=True)
@given(specs=st.lists(st.tuples(st.integers(0, 39), st.integers(1, 40),
                               st.sampled_from(["ADDRESS", "PHONE", "CARD"])), min_size=1, max_size=30))
def test_full_mask_coverage_is_the_union_of_eligible_candidates(specs):
    source = "x" * 40
    risk = {"ADDRESS": RiskLevel.MEDIUM, "PHONE": RiskLevel.HIGH, "CARD": RiskLevel.CRITICAL}
    candidates = [DetectionResult(label, source[start:min(40, start + length)], start,
                                  min(40, start + length), risk[label], confidence=1.0)
                  for start, length, label in specs]
    policy = policy_for(ProcessingMode.STRICT)
    selected = resolve_overlaps(candidates, policy=policy)
    fragments = protection_remainders(source, candidates, selected, policy, lambda label: "redact")
    final = resolve_overlaps([*selected, *fragments], policy=policy)
    expected = {i for d in candidates for i in range(d.start, d.end)}
    actual = {i for d in final for i in range(d.start, d.end)}
    assert actual == expected
    assert all(a.end <= b.start for a, b in zip(final, final[1:]))
    assert all(any(d is winner for d in final) for winner in selected)
    for fragment in fragments:
        assert fragment.text == source[fragment.start:fragment.end]
        parent = fragment.extra["overlap_parent"]["source_span"]
        assert parent[0] <= fragment.start < fragment.end <= parent[1]


@settings(max_examples=300, deadline=None, derandomize=True)
@given(specs=st.lists(st.tuples(st.integers(0, 39), st.integers(1, 40),
                               st.sampled_from(["ADDRESS", "PHONE", "CARD"]),
                               st.sampled_from([0.1, 0.5, 0.7, 0.9, 1.0])), min_size=1, max_size=30),
       mode=st.sampled_from(list(ProcessingMode)))
def test_coverage_respects_block_thresholds_in_every_mode(specs, mode):
    source = "x" * 40
    risk = {"ADDRESS": RiskLevel.MEDIUM, "PHONE": RiskLevel.HIGH, "CARD": RiskLevel.CRITICAL}
    candidates = [DetectionResult(label, source[start:min(40, start + length)], start,
                                  min(40, start + length), risk[label], confidence=confidence)
                  for start, length, label, confidence in specs]
    policy = policy_for(mode)
    selected = resolve_overlaps(candidates, policy=policy)
    fragments = protection_remainders(source, candidates, selected, policy, lambda label: "redact")
    final = resolve_overlaps([*selected, *fragments], policy=policy)
    expected = {i for d in candidates if policy.decide(d.risk_level, d.confidence) == Action.BLOCK
                for i in range(d.start, d.end)}
    actual = {i for d in final if policy.decide(d.risk_level, d.confidence) == Action.BLOCK
              for i in range(d.start, d.end)}
    assert actual == expected
    assert all(a.end <= b.start for a, b in zip(final, final[1:]))
    assert all(any(d is winner for d in final) for winner in selected
               if policy.decide(winner.risk_level, winner.confidence) == Action.BLOCK)
