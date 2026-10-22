import json

import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.review.feedback import apply_feedback
from ko_pii.review.queue import ReviewQueue, Verdict


def populate(path):
    queue = ReviewQueue(str(path))
    item = queue.enqueue_detection(DetectionResult("PERSON", "홍길동", 0, 3, RiskLevel.HIGH, confidence=0.6))
    return queue, item


@pytest.mark.parametrize("verdict, filename, attribute", [
    (Verdict.FP, "common_words_additions.txt", "common_word_candidates"),
    (Verdict.FN, "names_to_add.txt", "name_candidates"),
])
def test_retracted_feedback_clears_owned_file(tmp_path, verdict, filename, attribute):
    queue, item = populate(tmp_path / "review.jsonl")
    queue.mark(item.id, verdict)
    output = tmp_path / "feedback"
    first = apply_feedback(queue.path, str(output), min_repeat=1)
    assert getattr(first, attribute) == ["홍길동"]
    unrelated = output / "keep.txt"
    unrelated.write_text("keep")
    queue.mark(item.id, Verdict.OK)
    current = apply_feedback(queue.path, str(output), min_repeat=1)
    assert not getattr(current, attribute)
    assert "홍길동" not in (output / filename).read_text(encoding="utf-8")
    assert unrelated.read_text() == "keep"
    assert json.loads((output / "summary.json").read_text())[attribute] == []
    apply_feedback(queue.path, str(output), min_repeat=1)
    assert "홍길동" not in (output / filename).read_text(encoding="utf-8")


@pytest.mark.parametrize("count", [0, -1, True, 0.5])
def test_invalid_repeat_has_no_output(tmp_path, count):
    with pytest.raises(ValueError, match="min_repeat"):
        apply_feedback(str(tmp_path / "absent"), str(tmp_path / "output"), count)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("change", [
    {"span": [-1, 3]}, {"span": [True, 3]}, {"confidence": float("nan")},
    {"confidence": "secret@example.com"}, {"verdict": "WRONG"}, {"evidence": "secret@example.com"},
    {"surprise": "lost-on-save"},
    {"confidence": 10 ** 400},
])
def test_bad_record_does_not_load_or_overwrite(tmp_path, change):
    path = tmp_path / "q.jsonl"
    _, item = populate(path)
    bad = {**item.to_dict(), "id": "bad", **change}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(bad) + "\n")
    original = path.read_bytes()
    queue = ReviewQueue(str(path))
    for _ in range(2):
        with pytest.raises(ValueError) as error:
            queue.mark(item.id, Verdict.OK)
        assert "secret@" not in str(error.value)
        assert queue._items == []
        assert path.read_bytes() == original


@pytest.mark.parametrize("suffix", ['{"id":"broken"\n', '[]\n', '{"id":"a","id":"b"}\n'])
def test_truncated_or_non_object_record_fails_closed(tmp_path, suffix):
    path = tmp_path / "q.jsonl"
    _, item = populate(path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(suffix)
    original = path.read_bytes()
    queue = ReviewQueue(str(path))
    with pytest.raises(ValueError, match="line 2"):
        queue.mark(item.id, Verdict.OK)
    assert path.read_bytes() == original
    assert not queue._items


def test_duplicate_id_is_not_silently_merged(tmp_path):
    path = tmp_path / "q.jsonl"
    _, item = populate(path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item.to_dict()) + "\n")
    with pytest.raises(ValueError, match="line 2"):
        ReviewQueue(str(path)).all()


def test_failed_save_preserves_memory_and_disk(tmp_path, monkeypatch):
    from ko_pii.io_ import atomic
    path = tmp_path / "q.jsonl"
    queue, item = populate(path)
    original = path.read_bytes()

    def fail(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(atomic.os, "replace", fail)
    with pytest.raises(OSError):
        queue.mark(item.id, Verdict.OK)
    assert queue.by_id(item.id).verdict is None
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_append_after_missing_trailing_newline(tmp_path):
    path = tmp_path / "q.jsonl"
    _, item = populate(path)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    queue = ReviewQueue(str(path))
    queue.enqueue_detection(DetectionResult("PERSON", "홍길동", 0, 3, RiskLevel.HIGH))
    assert len(ReviewQueue(str(path))) == 2
    before = path.read_bytes()
    with pytest.raises(ValueError, match="verdict"):
        queue.mark(item.id, "TYPO")
    assert path.read_bytes() == before


def test_no_detection_does_not_claim_absence():
    result = Anonymizer(include=["RRN"]).process("주민번호: 800918-3414327")
    assert not result.detections
    assert "식별 정보 없음" not in result.summary["combined_rationale"]
    assert result.summary["detection_scope"]["include"] == ["RRN"]
    assert not result.summary["detection_scope"]["input_empty"]
    assert Anonymizer(mode=ProcessingMode.AUDIT).process("").summary["detection_scope"]["input_empty"]


def test_invalid_unicode_append_preserves_existing_file(tmp_path):
    path = tmp_path / "q.jsonl"
    queue, _ = populate(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Unicode"):
        queue.enqueue_detection(DetectionResult("PERSON", "\ud800", 0, 1, RiskLevel.HIGH))
    assert path.read_bytes() == before
    assert len(queue) == 1


@pytest.mark.parametrize("text", ["a\nb", " # ignored", "   "])
def test_feedback_rejects_ambiguous_lines_before_writing(tmp_path, text):
    queue = ReviewQueue(str(tmp_path / "q.jsonl"))
    item = queue.enqueue_detection(DetectionResult("PERSON", text, 0, len(text), RiskLevel.HIGH))
    queue.mark(item.id, Verdict.FP)
    output = tmp_path / "patches"
    with pytest.raises(ValueError, match="single non-comment"):
        apply_feedback(queue.path, str(output), min_repeat=1)
    assert not output.exists()
