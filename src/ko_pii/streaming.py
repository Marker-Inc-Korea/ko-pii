"""Bounded pre-forward handling for chunked text.

PII can be split across arbitrary transport chunks. Releasing each chunk after
scanning it independently therefore cannot guarantee that a complete identifier
was inspected. ``PreForwardAnonymizer`` buffers a bounded message and releases
only the anonymized final result.
"""
from __future__ import annotations

from dataclasses import dataclass

from ko_pii.anonymizer import AnonymizationResult, Anonymizer


class StreamBufferClosed(RuntimeError):
    """Raised when a finalized, aborted, or failed buffer is reused."""


class StreamBufferLimitExceeded(ValueError):
    """Raised after a buffer exceeds its configured character budget."""


@dataclass(frozen=True)
class StreamBufferStatus:
    """Content-free state safe to expose in metrics or logs."""

    buffered_chars: int
    max_chars: int
    closed: bool
    failed: bool

    @property
    def remaining_chars(self) -> int:
        return max(0, self.max_chars - self.buffered_chars)


class PreForwardAnonymizer:
    """Accumulate chunks and anonymize once before any content is forwarded.

    ``feed`` never returns source text. Call ``finalize`` exactly once and use
    only the returned ``AnonymizationResult.text`` downstream. This deliberately
    favors a defensible privacy boundary over token-by-token latency.
    """

    def __init__(
        self,
        anonymizer: Anonymizer | None = None,
        *,
        max_chars: int = 2_000_000,
    ) -> None:
        if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 1:
            raise ValueError("max_chars must be a positive integer")
        self.anonymizer = anonymizer or Anonymizer()
        self.max_chars = max_chars
        self._chunks: list[str] = []
        self._chars = 0
        self._closed = False
        self._failed = False

    @property
    def status(self) -> StreamBufferStatus:
        return StreamBufferStatus(
            buffered_chars=self._chars,
            max_chars=self.max_chars,
            closed=self._closed,
            failed=self._failed,
        )

    def feed(self, chunk: str) -> StreamBufferStatus:
        """Buffer one text chunk without returning any source content."""
        self._ensure_open()
        if not isinstance(chunk, str):
            raise TypeError(f"feed() expects str, got {type(chunk).__name__}")
        if self._chars + len(chunk) > self.max_chars:
            self._chunks.clear()
            self._chars = 0
            self._failed = True
            self._closed = True
            raise StreamBufferLimitExceeded(
                f"chunked input exceeds max_chars={self.max_chars}; no content was released"
            )
        self._chunks.append(chunk)
        self._chars += len(chunk)
        return self.status

    def finalize(self) -> AnonymizationResult:
        """Close the buffer and return one anonymized result."""
        self._ensure_open()
        source = "".join(self._chunks)
        self._chunks.clear()
        self._chars = 0
        self._closed = True
        try:
            return self.anonymizer.process(source)
        except Exception:
            self._failed = True
            raise

    def abort(self) -> StreamBufferStatus:
        """Discard all buffered source text and close the session."""
        self._ensure_open()
        self._chunks.clear()
        self._chars = 0
        self._closed = True
        return self.status

    def _ensure_open(self) -> None:
        if self._closed:
            raise StreamBufferClosed("pre-forward buffer is already closed")


__all__ = [
    "PreForwardAnonymizer",
    "StreamBufferClosed",
    "StreamBufferLimitExceeded",
    "StreamBufferStatus",
]
