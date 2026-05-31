"""TF-IDF + Logistic Regression — 초고속 베이스라인.

목표: ~0.5ms/doc, F1 ~0.85+
용도: BERT 무거우면 사전 필터로 사용
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)


def load_jsonl(path: Path) -> tuple[list[str], np.ndarray]:
    texts, labels = [], []
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            texts.append(r["text"])
            labels.append(r["label"])
    return texts, np.array(labels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("data/classifier"))
    ap.add_argument("--output", type=Path, default=Path("models/pii_tfidf_v1.pkl"))
    ap.add_argument("--analyzer", default="char_wb", choices=["word", "char", "char_wb"])
    ap.add_argument("--ngram-min", type=int, default=2)
    ap.add_argument("--ngram-max", type=int, default=5)
    ap.add_argument("--max-features", type=int, default=200_000)
    ap.add_argument("--C", type=float, default=1.0)
    ap.add_argument("--max-iter", type=int, default=200)
    args = ap.parse_args()

    print("=== loading ===")
    Xtr, ytr = load_jsonl(args.data_dir / "train.jsonl")
    Xva, yva = load_jsonl(args.data_dir / "val.jsonl")
    Xte, yte = load_jsonl(args.data_dir / "test.jsonl")
    print(f"  train={len(Xtr)} val={len(Xva)} test={len(Xte)} pos_rate(train)={ytr.mean():.3f}")

    print(f"\n=== fitting TF-IDF ({args.analyzer}, ngram {args.ngram_min}-{args.ngram_max}) ===")
    t = time.time()
    vec = TfidfVectorizer(
        analyzer=args.analyzer,
        ngram_range=(args.ngram_min, args.ngram_max),
        max_features=args.max_features,
        min_df=2,
        sublinear_tf=True,
    )
    Xtr_v = vec.fit_transform(Xtr)
    Xva_v = vec.transform(Xva)
    Xte_v = vec.transform(Xte)
    print(f"  vocab size: {len(vec.vocabulary_)}, fit+transform: {time.time()-t:.1f}s")

    print(f"\n=== fitting LogReg (C={args.C}) ===")
    t = time.time()
    clf = LogisticRegression(C=args.C, max_iter=args.max_iter, n_jobs=-1, solver="liblinear")
    clf.fit(Xtr_v, ytr)
    print(f"  fit: {time.time()-t:.1f}s")

    def evaluate(name, X, y):
        probs = clf.predict_proba(X)[:, 1]
        pred = (probs >= 0.5).astype(int)
        acc = accuracy_score(y, pred)
        f1 = f1_score(y, pred)
        p, r, _, _ = precision_recall_fscore_support(y, pred, average="binary")
        auc = roc_auc_score(y, probs)
        print(f"\n{name}: acc={acc:.4f} f1={f1:.4f} precision={p:.4f} recall={r:.4f} auc={auc:.4f}")
        return probs

    evaluate("val ", Xva_v, yva)
    test_probs = evaluate("test", Xte_v, yte)

    # threshold sweep on test (필터 모드 운영점)
    print(f"\n=== threshold sweep (test) ===")
    print(f"{'thr':>5} | {'prec':>5} | {'recall':>6} | {'f1':>5} | {'skip%':>5}")
    print("-" * 40)
    for thr in [0.20, 0.30, 0.40, 0.50, 0.60, 0.70]:
        pred = (test_probs >= thr).astype(int)
        tp = int(((pred == 1) & (yte == 1)).sum())
        fp = int(((pred == 1) & (yte == 0)).sum())
        fn = int(((pred == 0) & (yte == 1)).sum())
        p_ = tp / (tp + fp) if tp + fp else 0
        r_ = tp / (tp + fn) if tp + fn else 0
        f1_ = 2 * p_ * r_ / (p_ + r_) if p_ + r_ else 0
        skip = ((pred == 0).mean()) * 100
        print(f"{thr:>5.2f} | {p_:>5.3f} | {r_:>6.3f} | {f1_:>5.3f} | {skip:>4.1f}%")

    # 필터 운영점 찾기 (recall 목표)
    print(f"\n=== filter operating points ===")
    for target in [0.99, 0.97, 0.95]:
        best = None
        for thr in np.arange(0.001, 0.95, 0.005):
            pred = (test_probs >= thr).astype(int)
            tp = int(((pred == 1) & (yte == 1)).sum())
            fp = int(((pred == 1) & (yte == 0)).sum())
            fn = int(((pred == 0) & (yte == 1)).sum())
            r_ = tp / (tp + fn) if tp + fn else 0
            p_ = tp / (tp + fp) if tp + fp else 0
            if r_ >= target and (best is None or p_ > best[1]):
                best = (thr, p_, r_, (pred == 0).mean())
        if best:
            thr, p_, r_, skip = best
            print(f"  target={target}: thr={thr:.3f} | precision={p_:.3f} | actual recall={r_:.3f} | skip={skip*100:.1f}%")

    # latency
    print(f"\n=== CPU latency ===")
    sample = Xte[0]
    # warmup
    for _ in range(5):
        v = vec.transform([sample])
        clf.predict_proba(v)
    # single
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        v = vec.transform([sample])
        clf.predict_proba(v)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    print(f"  single: median={times[50]:.3f}ms  p95={times[95]:.3f}ms  p99={times[99]:.3f}ms")
    # batch
    t0 = time.perf_counter()
    v = vec.transform(Xte[:1000])
    clf.predict_proba(v)
    elapsed = time.perf_counter() - t0
    print(f"  batch (1000 chunks): {elapsed*1000:.1f}ms total | {elapsed:.3f}s | {1000/elapsed:.0f} chunks/s")

    # save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as f:
        pickle.dump({"vectorizer": vec, "model": clf, "config": vars(args)}, f)
    size_mb = args.output.stat().st_size / 1024 / 1024
    print(f"\nsaved: {args.output} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
