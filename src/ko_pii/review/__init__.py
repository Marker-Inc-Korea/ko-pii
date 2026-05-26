"""검토 워크플로우 — REVIEW 큐 저장 + 사용자 피드백 학습.

룰 기반 PII 검출의 한계 (특히 PERSON 자연어) 를 *사람 검토* 로 보완하기 위한
모듈. 검토 결과 (OK/FP/FN) 를 영구 저장하고, FP 표시된 토큰은 자동으로
``common_words`` 사전 후보로 등록 → 다음 실행부터 점진 개선.
"""
from ko_pii.review.queue import (
    ReviewQueue,
    ReviewItem,
    Verdict,
)
from ko_pii.review.feedback import (
    apply_feedback,
    FeedbackSummary,
)

__all__ = [
    "ReviewQueue", "ReviewItem", "Verdict",
    "apply_feedback", "FeedbackSummary",
]
