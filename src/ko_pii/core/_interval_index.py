"""Private overlap queries for ordered detector passes, including nested spans."""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable


class ForwardIntervalIndex:
    """Snapshot arbitrary intervals, then accept forward-only queries/additions.

    Later passes build a new snapshot. Within a pass, accepted intervals start
    no later than subsequent queries, so their largest end is sufficient.
    """

    def __init__(self, spans: Iterable[tuple[int, int]]) -> None:
        self._starts: list[int] = []
        self._ends: list[int] = []
        for start, end in sorted(spans):
            self._starts.append(start)
            self._ends.append(max(self._ends[-1], end) if self._ends else end)
        self._added_end: int | None = None
        self._last_start: int | None = None

    def _forward(self, start: int) -> None:
        if self._last_start is not None and start < self._last_start:
            raise ValueError("interval pass must move forward")
        self._last_start = start

    def overlaps(self, start: int, end: int, *, margin: int = 0) -> bool:
        self._forward(start)
        position = bisect_left(self._starts, end + margin) - 1
        return (
            (position >= 0 and self._ends[position] > start - margin)
            or (self._added_end is not None and self._added_end > start - margin)
        )

    def add(self, start: int, end: int) -> None:
        self._forward(start)
        self._added_end = max(self._added_end, end) if self._added_end is not None else end
