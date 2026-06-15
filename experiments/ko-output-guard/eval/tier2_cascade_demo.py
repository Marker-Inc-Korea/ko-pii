"""Tier-2 cascade 효과 측정 — TF-IDF toxicity 분류기로 결정론 recall 을 보강.

결정론 TOXICITY 는 외부(unsmile)에서 recall ≈32% 에 그친다(external_toxicity.py).
여기서는 unsmile train 으로 가벼운 char-ngram TF-IDF 분류기를 학습해 Tier-2 로 cascade
(결정론이 비운 카테고리만 호출)했을 때 recall/FPR 이 어떻게 바뀌는지 측정한다.

이 분류기는 *데모*다 — production 에서는 도경 보유 모델(bge-m3/Solar 기반 judge,
또는 unsmile-tuned BERT)을 같은 인터페이스(Guard(tier2={Category.TOXICITY: fn}))로
주입한다. sklearn 필요.

실행:
    PYTHONPATH=src:<ko-pii>/src:<ko-prompt-guard>/src python eval/tier2_cascade_demo.py
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

from ko_output_guard import Category, Guard, Verdict

_DIR = Path("/data1/mk04/eval_external")
_HATE = ["여성/가족", "남성", "성소수자", "인종/국적", "연령", "지역", "종교", "기타 혐오"]


def _rows(split: str) -> list[dict[str, str]]:
    with (_DIR / f"unsmile_{split}_v1.0.tsv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def main() -> int:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
    except ImportError:
        print("sklearn 미설치 — 데모 분류기를 만들 수 없음(인터페이스는 guard.py 에 존재).")
        return 0

    train = _rows("train")
    x_tr = [r["문장"] for r in train]
    y_tr = [0 if r.get("clean") == "1" else 1 for r in train]
    clf = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )
    clf.fit(x_tr, y_tr)

    def tox_clf(text: str) -> bool:
        return bool(clf.predict([text])[0] == 1)

    g0 = Guard()
    g2 = Guard(tier2={Category.TOXICITY: tox_clf})
    s: collections.Counter[str] = collections.Counter()
    for r in _rows("valid"):
        t = r["문장"]
        c0 = g0.check(t).verdict is not Verdict.SAFE
        c2 = g2.check(t).verdict is not Verdict.SAFE
        if r.get("clean") == "1":
            s["clean"] += 1
            s["clean_c0"] += c0
            s["clean_c2"] += c2
        else:
            s["tox"] += 1
            s["tox_c0"] += c0
            s["tox_c2"] += c2

    def pct(a: int, b: int) -> str:
        return f"{a / b * 100:.1f}%" if b else "n/a"

    fpr0, fpr2 = pct(s["clean_c0"], s["clean"]), pct(s["clean_c2"], s["clean"])
    rec0, rec2 = pct(s["tox_c0"], s["tox"]), pct(s["tox_c2"], s["tox"])
    print("=== Tier-2 cascade (TF-IDF char-ngram) × unsmile valid ===")
    print(f"FPR    결정론 {fpr0} → cascade {fpr2}")
    print(f"Recall 결정론 {rec0} → cascade {rec2}")
    print("\nfast-path 유지: 결정론이 잡은 건 분류기 호출 생략. recall 격차를 분류기가 메운다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
