"""평가: 블루팀(정상 쿼리 → 과탐/FPR) + 레드팀(공격 → 탐지/recall) + P/R/F1.

    .venv/bin/python -m eval.measure   (또는  python eval/measure.py)

블루팀이 핵심: 보안 가드는 공격을 막는 것만큼 정상 쿼리를 안 막는 것이 중요하다.
FPR(정상인데 BLOCK) 과 recall(공격인데 통과)을 한 화면에서 본다.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import ATTACK, BENIGN, POLICY  # noqa: E402

from ko_sqlguard import Guard, Verdict  # noqa: E402

_GUARD = Guard(POLICY)


def _blocked(sql: str) -> bool:
    return _GUARD.check(sql).verdict is Verdict.BLOCK


def main() -> None:
    # 블루팀 — 정상 쿼리는 not BLOCK 이어야. BLOCK 이면 과탐(FP).
    fp = [(cat, sql) for cat, sql in BENIGN if _blocked(sql)]
    tn = len(BENIGN) - len(fp)
    # 레드팀 — 공격은 BLOCK 이어야. not BLOCK 이면 누락(FN).
    tp = sum(1 for _cat, sql in ATTACK if _blocked(sql))
    fn = [(cat, sql) for cat, sql in ATTACK if not _blocked(sql)]

    n_fp, n_fn = len(fp), len(fn)
    fpr = n_fp / len(BENIGN) if BENIGN else 0.0
    precision = tp / (tp + n_fp) if (tp + n_fp) else 0.0
    recall = tp / (tp + n_fn) if (tp + n_fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print("=" * 64)
    print(f"블루팀 — 정상 분석 쿼리 {len(BENIGN)}개 (과탐 측정)")
    print(f"  통과(TN) {tn}/{len(BENIGN)}   과탐(FP) {n_fp}/{len(BENIGN)}   FPR {fpr:.1%}")
    if fp:
        for cat, sql in fp:
            print(f"    ✗ FP [{cat}] {sql[:62]}")
    print("=" * 64)
    print(f"레드팀 — 공격/우회 {len(ATTACK)}개 (탐지 측정)")
    print(f"  차단(TP) {tp}/{len(ATTACK)}   누락(FN) {n_fn}/{len(ATTACK)}   Recall {recall:.1%}")
    if fn:
        for cat, sql in fn:
            print(f"    ✗ MISS [{cat}] {sql[:62]}")
    # 범주별 누락
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for cat, sql in ATTACK:
        by_cat[cat][0] += 1
        by_cat[cat][1] += _blocked(sql)
    print("=" * 64)
    print(f"종합  Precision {precision:.3f}  Recall {recall:.3f}  F1 {f1:.3f}  FPR {fpr:.1%}")
    print("=" * 64)


if __name__ == "__main__":
    main()
