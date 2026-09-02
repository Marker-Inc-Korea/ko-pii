import pytest

from ko_pii import (
    Anonymizer,
    PreForwardAnonymizer,
    ProcessingMode,
    StreamBufferClosed,
    StreamBufferLimitExceeded,
)


def test_cross_chunk_identifier_is_anonymized_before_release() -> None:
    stream = PreForwardAnonymizer(
        Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
    )

    first = stream.feed("주민번호 880101-")
    second = stream.feed("1234568 입니다")

    assert first.buffered_chars == len("주민번호 880101-")
    assert second.closed is False
    result = stream.finalize()
    assert "880101-1234568" not in result.text
    assert "<RRN_1>" in result.text
    assert stream.status.closed is True


def test_limit_failure_discards_buffer_and_closes_session() -> None:
    stream = PreForwardAnonymizer(max_chars=5)
    stream.feed("1234")

    with pytest.raises(StreamBufferLimitExceeded, match="no content was released"):
        stream.feed("56")

    assert stream.status.buffered_chars == 0
    assert stream.status.failed is True
    assert stream.status.closed is True
    with pytest.raises(StreamBufferClosed):
        stream.finalize()


def test_abort_discards_content_and_prevents_reuse() -> None:
    stream = PreForwardAnonymizer()
    stream.feed("010-1234-5678")
    status = stream.abort()

    assert status.buffered_chars == 0
    assert status.closed is True
    assert status.failed is False
    with pytest.raises(StreamBufferClosed):
        stream.feed("more")


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_max_chars_must_be_positive_integer(value: object) -> None:
    with pytest.raises(ValueError):
        PreForwardAnonymizer(max_chars=value)  # type: ignore[arg-type]


def test_feed_rejects_non_text_without_closing() -> None:
    stream = PreForwardAnonymizer()
    with pytest.raises(TypeError):
        stream.feed(b"text")  # type: ignore[arg-type]
    assert stream.status.closed is False
