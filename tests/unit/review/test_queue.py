from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.review.queue import ReviewQueue, Verdict


def _det(label="PERSON", text="홍길동", start=0, end=3):
    return DetectionResult(
        label=label, text=text, start=start, end=end,
        risk_level=RiskLevel.HIGH, confidence=0.55,
        evidence=["pos:surname"], legal_basis="개인정보보호법 제2조",
    )


class TestReviewQueueBasics:
    def test_enqueue_single(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "queue.jsonl"))
        q.enqueue_detection(_det(), document="doc1.txt")
        assert len(q) == 1
        item = q.pending()[0]
        assert item.label == "PERSON"
        assert item.text == "홍길동"
        assert item.verdict is None

    def test_persistence(self, tmp_path):
        path = str(tmp_path / "queue.jsonl")
        q1 = ReviewQueue(path)
        q1.enqueue_detection(_det(text="이순신"), document="d.txt")
        # 새 인스턴스에서 다시 로드
        q2 = ReviewQueue(path)
        assert len(q2) == 1
        assert q2.pending()[0].text == "이순신"

    def test_mark_verdict(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "queue.jsonl"))
        item = q.enqueue_detection(_det(), document="d.txt")
        assert q.mark(item.id, Verdict.FP, by="reviewer1", note="동음이의어")
        # 재로드 후에도 마킹 보존
        q2 = ReviewQueue(q.path)
        marked = q2.by_id(item.id)
        assert marked.verdict == "FP"
        assert marked.verdict_by == "reviewer1"
        assert marked.verdict_note == "동음이의어"

    def test_pending_excludes_marked(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        a = q.enqueue_detection(_det(text="홍길동"))
        b = q.enqueue_detection(_det(text="김민수"))
        q.mark(a.id, Verdict.OK)
        pending = q.pending()
        assert len(pending) == 1
        assert pending[0].id == b.id

    def test_stats(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        a = q.enqueue_detection(_det(text="A"))
        b = q.enqueue_detection(_det(text="B"))
        c = q.enqueue_detection(_det(text="C"))
        q.mark(a.id, Verdict.OK)
        q.mark(b.id, Verdict.FP)
        s = q.stats()
        assert s["total"] == 3
        assert s["pending"] == 1
        assert s["OK"] == 1
        assert s["FP"] == 1


class TestEnqueueReviewRecords:
    def test_from_anonymization_result(self, tmp_path):
        from ko_pii import Anonymizer, ProcessingMode
        anon = Anonymizer(mode=ProcessingMode.PERMISSIVE)
        result = anon.process("주민번호 880101-1234567")  # 후-2020 → REVIEW
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        items = q.enqueue_review_records(result.review_items(), document="doc")
        assert len(items) >= 1
        assert all(it.verdict is None for it in items)
