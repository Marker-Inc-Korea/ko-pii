"""Protect uncovered parts of complete-replacement candidates after selection."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import heapq

from ko_pii.core.modes import Action, ModePolicy
from ko_pii.core.types import DetectionResult


_COMPLETE_REPLACEMENTS = frozenset({"redact", "tokenize", "asterisk", "hashed"})


def protection_remainders(
    text: str,
    candidates: list[DetectionResult],
    selected: list[DetectionResult],
    policy: ModePolicy,
    strategy_for: Callable[[str], str],
) -> list[DetectionResult]:
    """Partition unassigned BLOCK coverage in O(n log n), without replacing winners.

    Fragments are derived protection intervals, not new standalone detector
    matches. Selected BLOCK spans keep their own strategy, including partial.
    """
    selected_ids = {id(item) for item in selected}
    parents = [item for item in candidates
               if id(item) not in selected_ids
               and policy.decide(item.risk_level, item.confidence) == Action.BLOCK
               and strategy_for(item.label) in _COMPLETE_REPLACEMENTS]
    if not parents:
        return []
    covered = [item for item in selected
               if policy.decide(item.risk_level, item.confidence) == Action.BLOCK]
    lower = min(item.start for item in parents)
    upper = max(item.end for item in parents)
    covered = sorted((item for item in covered if item.start < upper and item.end > lower),
                     key=lambda item: (item.start, item.end))
    points = sorted({position for item in [*parents, *covered]
                     for position in (item.start, item.end)})
    starts = sorted(range(len(parents)), key=lambda i: (parents[i].start, i))
    active: list[tuple[int, float, int, int, int]] = []
    pieces: list[tuple[int, int, int]] = []
    incoming = occupied = 0
    for begin, end in zip(points, points[1:]):
        while incoming < len(starts) and parents[starts[incoming]].start <= begin:
            index = starts[incoming]
            parent = parents[index]
            heapq.heappush(active, (-int(parent.risk_level), -parent.confidence,
                                   -(parent.end - parent.start), parent.start, index))
            incoming += 1
        while active and parents[active[0][-1]].end <= begin:
            heapq.heappop(active)
        while occupied < len(covered) and covered[occupied].end <= begin:
            occupied += 1
        if not active or (occupied < len(covered) and covered[occupied].start <= begin):
            continue
        owner = active[0][-1]
        if pieces and pieces[-1][1] == begin and pieces[-1][2] == owner:
            pieces[-1] = (pieces[-1][0], end, owner)
        else:
            pieces.append((begin, end, owner))
    return [replace(
        parents[owner], start=begin, end=end, text=text[begin:end],
        evidence=[*parents[owner].evidence, "protection:overlap_remainder"],
        subrule_id="protection.overlap-remainder.v1",
        extra={**parents[owner].extra, "overlap_parent": {
            "label": parents[owner].label,
            "source_span": [parents[owner].start, parents[owner].end],
        }},
    ) for begin, end, owner in pieces]
