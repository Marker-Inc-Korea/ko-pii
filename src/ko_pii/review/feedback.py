"""사용자 피드백 → 사전·룰 학습.

검토 큐에서 ``verdict`` 가 설정된 항목들을 분석하여:

- **FP (false positive)** 표시된 토큰: 다음 실행에서 다시 잡지 않도록 후보로 등록
  - PERSON FP 였으면 → ``common_words`` 후보로 제안
  - 카테고리별 패턴 분석은 별도 작업
- **FN (false negative)** 표시된 토큰: 사용자 사전에 추가하여 다음부터 잡도록

학습은 *자동 적용* 이 아니라 **patch 파일 생성** 후 사용자 검토 → 수동 반영.
잘못된 학습이 누적되는 것을 방지.

출력: ``feedback_patches/`` 디렉토리에:
- ``common_words_additions.txt`` — PERSON FP 들 (한 줄당 1단어)
- ``names_to_add.txt`` — FN 으로 표시된 이름들
- ``summary.json`` — 통계
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeedbackSummary:
    fp_count: int = 0
    ok_count: int = 0
    fn_count: int = 0
    pending: int = 0
    common_word_candidates: list[str] = field(default_factory=list)
    name_candidates: list[str] = field(default_factory=list)
    fp_by_label: dict[str, int] = field(default_factory=dict)


def apply_feedback(
    queue_path: str,
    output_dir: str,
    min_repeat: int = 2,
) -> FeedbackSummary:
    """검토 큐에서 verdict 마킹을 읽어 패치 파일 생성.

    Parameters
    ----------
    queue_path :
        :class:`ReviewQueue` 의 JSONL 파일 경로.
    output_dir :
        패치 파일이 저장될 디렉토리.
    min_repeat :
        같은 토큰이 ``min_repeat`` 회 이상 FP 마킹되어야 후보로 등록 (오류 표시
        한 번에 사전이 오염되는 것 방지).
    """
    from ko_pii.review.queue import ReviewQueue
    q = ReviewQueue(queue_path)
    items = q.all()

    summary = FeedbackSummary()
    fp_tokens: Counter[tuple[str, str]] = Counter()  # (label, text)
    fn_tokens: Counter[tuple[str, str]] = Counter()

    for item in items:
        if item.verdict is None:
            summary.pending += 1
        elif item.verdict == "FP":
            summary.fp_count += 1
            summary.fp_by_label[item.label] = summary.fp_by_label.get(item.label, 0) + 1
            fp_tokens[(item.label, item.text)] += 1
        elif item.verdict == "OK":
            summary.ok_count += 1
        elif item.verdict == "FN":
            summary.fn_count += 1
            fn_tokens[(item.label, item.text)] += 1

    # PERSON FP → common_words 후보
    person_fps = sorted(
        text for (label, text), n in fp_tokens.items()
        if label == "PERSON" and n >= min_repeat
    )
    summary.common_word_candidates = person_fps

    # 모든 FN → 이름 후보 (PERSON 가정)
    summary.name_candidates = sorted(
        text for (label, text), _n in fn_tokens.items() if label == "PERSON"
    )

    os.makedirs(output_dir, exist_ok=True)

    if person_fps:
        with open(os.path.join(output_dir, "common_words_additions.txt"),
                  "w", encoding="utf-8") as f:
            f.write("# ko-pii 검토 큐에서 자동 생성된 일반 단어 후보\n")
            f.write("# 검토 후 src/ko_pii/dictionaries/common_words.py 에 반영하세요.\n")
            for w in person_fps:
                f.write(w + "\n")

    if summary.name_candidates:
        with open(os.path.join(output_dir, "names_to_add.txt"),
                  "w", encoding="utf-8") as f:
            f.write("# 사용자가 FN 으로 표시한 이름들\n")
            f.write("# 사용자 사전 (사이트별 names.txt) 에 추가 후 person 검출 부스트로 활용 가능\n")
            for n in summary.name_candidates:
                f.write(n + "\n")

    with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "fp_count": summary.fp_count,
                "ok_count": summary.ok_count,
                "fn_count": summary.fn_count,
                "pending": summary.pending,
                "common_word_candidates": summary.common_word_candidates,
                "name_candidates": summary.name_candidates,
                "fp_by_label": summary.fp_by_label,
            },
            f, ensure_ascii=False, indent=2,
        )

    return summary
