import json
import os

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.review.feedback import apply_feedback
from ko_pii.review.queue import ReviewQueue, Verdict


def _det(label, text):
    return DetectionResult(
        label=label, text=text, start=0, end=len(text),
        risk_level=RiskLevel.HIGH, confidence=0.6,
    )


class TestApplyFeedback:
    def test_fp_aggregation(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        # 같은 FP 가 3번 나오면 후보 — min_repeat=2
        for _ in range(3):
            it = q.enqueue_detection(_det("PERSON", "검토"))
            q.mark(it.id, Verdict.FP, note="일반 단어")
        out_dir = tmp_path / "patches"
        summary = apply_feedback(q.path, str(out_dir), min_repeat=2)
        assert summary.fp_count == 3
        assert "검토" in summary.common_word_candidates

        # 패치 파일 생성됨
        assert os.path.exists(out_dir / "common_words_additions.txt")
        body = (out_dir / "common_words_additions.txt").read_text(encoding="utf-8")
        assert "검토" in body

    def test_below_min_repeat(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        it = q.enqueue_detection(_det("PERSON", "한번만FP"))
        q.mark(it.id, Verdict.FP)
        summary = apply_feedback(q.path, str(tmp_path / "patches"), min_repeat=2)
        assert "한번만FP" not in summary.common_word_candidates

    def test_fn_names_captured(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        it = q.enqueue_detection(_det("PERSON", "특이한이름"))
        q.mark(it.id, Verdict.FN, note="검출 실패한 이름")
        out_dir = tmp_path / "patches"
        summary = apply_feedback(q.path, str(out_dir))
        assert "특이한이름" in summary.name_candidates
        assert os.path.exists(out_dir / "names_to_add.txt")

    def test_summary_json_written(self, tmp_path):
        q = ReviewQueue(str(tmp_path / "q.jsonl"))
        it = q.enqueue_detection(_det("PERSON", "x"))
        q.mark(it.id, Verdict.OK)
        out_dir = tmp_path / "patches"
        apply_feedback(q.path, str(out_dir))
        with open(out_dir / "summary.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["ok_count"] == 1
