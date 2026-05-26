"""Evaluate openai/privacy-filter (ONNX) on KLUE-NER PS using the same
matching/filter logic as ko-pii's `evaluate_person` so the F1 numbers are
directly comparable to the cloud session's reported ko-pii F1 = 0.376
(korean_only mode, partial overlap, Korean-fullname filter 3-5자 한글).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ko_pii.eval.klue_ner import load_klue_ner
from ko_pii.eval.model_comparison import HFPrivacyDetector


def _is_valid_korean_fullname(text: str, *, korean_only: bool) -> bool:
    if len(text) < 3 or len(text) > 5:
        return False
    if not all("가" <= ch <= "힣" for ch in text):
        return False
    if korean_only:
        from ko_pii.context.name_origin import classify_name_origin
        return classify_name_origin(text) == "korean"
    return True


def evaluate_openai_on_klue_ner(
    klue_path: str,
    *,
    backend: str = "onnx",
    device: str = "cpu",
    cache_dir: str = "./models",
    korean_only: bool = True,
    mode: str = "partial",  # partial | strict
    sample_limit: int | None = None,
) -> dict:
    detector = HFPrivacyDetector(
        "openai/privacy-filter", backend=backend, device=device, cache_dir=cache_dir,
    )
    sentences = load_klue_ner(klue_path)
    if sample_limit:
        sentences = sentences[:sample_limit]
    print(f"Sentences: {len(sentences)}, device: {detector.device}", file=sys.stderr)

    tp = fp = fn = 0
    t0 = time.time()
    for idx, sent in enumerate(sentences):
        if idx and idx % 200 == 0:
            elapsed = time.time() - t0
            print(f"  {idx}/{len(sentences)} ({elapsed:.0f}s, {idx/elapsed:.1f} sent/sec)",
                  file=sys.stderr)
        gold = [
            s for s in sent.spans
            if s.label == "PS" and _is_valid_korean_fullname(s.text, korean_only=korean_only)
        ]
        raw_pred = detector.detect(sent.text)
        # private_person predictions, same fullname filter applied
        pred = [
            p for p in raw_pred
            if p.label == "private_person"
            and _is_valid_korean_fullname(p.text.strip(), korean_only=korean_only)
        ]

        matched_pred: set[int] = set()
        for g in gold:
            hit = -1
            for i, p in enumerate(pred):
                if i in matched_pred:
                    continue
                if mode == "strict":
                    if p.start == g.start and (p.end == g.end or len(p.text.strip()) == g.end - g.start):
                        hit = i
                        break
                else:
                    if p.start < g.end and g.start < p.end:
                        hit = i
                        break
            if hit >= 0:
                tp += 1
                matched_pred.add(hit)
            else:
                fn += 1
        for i, p in enumerate(pred):
            if i not in matched_pred:
                fp += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "sentences": len(sentences),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path", default="data/klue_ner/klue-ner-v1.1_dev.tsv", nargs="?")
    p.add_argument("--korean-only", action="store_true", default=True)
    p.add_argument("--include-foreign", dest="korean_only", action="store_false")
    p.add_argument("--mode", choices=["partial", "strict"], default="partial")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "dml"])
    p.add_argument("--cache-dir", default="./models")
    args = p.parse_args()

    print(f"=== openai/privacy-filter on KLUE-NER PS ===", file=sys.stderr)
    print(f"  korean_only={args.korean_only}, mode={args.mode}, device={args.device}",
          file=sys.stderr)

    r = evaluate_openai_on_klue_ner(
        args.path,
        device=args.device,
        cache_dir=args.cache_dir,
        korean_only=args.korean_only,
        mode=args.mode,
        sample_limit=args.limit,
    )
    print()
    print(f"openai/privacy-filter — KLUE-NER PS (korean_only={args.korean_only})")
    print(f"  Sentences: {r['sentences']}")
    print(f"  TP={r['tp']}  FP={r['fp']}  FN={r['fn']}")
    print(f"  Precision = {r['precision']:.3f}")
    print(f"  Recall    = {r['recall']:.3f}")
    print(f"  F1        = {r['f1']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
