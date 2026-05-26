"""inject_pii_corpus.py 로 생성한 JSONL 코퍼스에 ko-pii vs openai/privacy-filter
양쪽을 평가.

실행:
    # 1. 코퍼스 생성
    python data/inject_pii_corpus.py -n 200 --seed 0

    # 2. 두 검출기 비교
    python data/eval_injected_corpus.py data/corpus/injected_pii_corpus.jsonl

핵심: GoldSpan/GoldDocument 형식으로 변환 후 `ko_pii.eval.metrics.score_corpus`
재사용. 한 코퍼스 → 한 번 로드 → 두 detector 호출 → 양쪽 표 출력.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.detect import detect_all
from ko_pii.eval.metrics import (
    BenchmarkReport,
    PerLabelMetrics,
    format_report,
    score_corpus,
)
from ko_pii.eval.synth import GoldDocument, GoldSpan


def load_injected_corpus(path: str | Path) -> list[GoldDocument]:
    docs: list[GoldDocument] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            spans = [
                GoldSpan(
                    label=s["label"], start=s["start"],
                    end=s["end"], text=s["text"],
                )
                for s in d["spans"]
            ]
            docs.append(GoldDocument(text=d["text"], spans=spans))
    return docs


def make_openai_predict(detector):
    from ko_pii.eval.model_comparison import OPENAI_TO_KPII

    def predict(text: str) -> list[DetectionResult]:
        out: list[DetectionResult] = []
        for s in detector.detect(text):
            mapped = OPENAI_TO_KPII.get(s.label)
            if not mapped:
                continue
            out.append(DetectionResult(
                label=mapped,
                text=s.text.strip(),
                start=s.start,
                end=s.end,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
            ))
        return out
    return predict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path", help="JSONL corpus (from inject_pii_corpus.py)")
    p.add_argument("--mode", choices=["partial", "strict"], default="partial")
    p.add_argument("--skip-openai", action="store_true",
                   help="ko-pii 만 평가 (openai 모델 로드 X)")
    p.add_argument("--cache-dir", default="./models")
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    print(f"Loading corpus: {args.path}", file=sys.stderr)
    corpus = load_injected_corpus(args.path)
    total_spans = sum(len(d.spans) for d in corpus)
    print(f"Docs: {len(corpus)}, gold spans: {total_spans}", file=sys.stderr)

    # ko-pii
    print("\n=== ko-pii (rules) ===", file=sys.stderr)
    t0 = time.time()
    kpii_report = score_corpus(corpus, detect_all, mode=args.mode)
    print(f"  ko-pii eval: {time.time()-t0:.1f}s", file=sys.stderr)
    print(format_report(kpii_report))

    if args.skip_openai:
        return 0

    # openai/privacy-filter
    print("\n=== openai/privacy-filter (ONNX) ===", file=sys.stderr)
    from ko_pii.eval.model_comparison import HFPrivacyDetector
    det = HFPrivacyDetector(
        "openai/privacy-filter", backend="onnx",
        device=args.device, cache_dir=args.cache_dir,
    )
    print(f"  device: {det.device}", file=sys.stderr)
    t0 = time.time()
    of_report = score_corpus(corpus, make_openai_predict(det), mode=args.mode)
    print(f"  openai eval: {time.time()-t0:.1f}s", file=sys.stderr)
    print(format_report(of_report))

    # Side-by-side micro summary
    print()
    print("=== Side-by-side (micro) ===")
    kp = kpii_report.micro()
    of = of_report.micro()
    print(f"ko-pii   : TP={kp.tp} FP={kp.fp} FN={kp.fn}  "
          f"P={kp.precision:.3f} R={kp.recall:.3f} F1={kp.f1:.3f}")
    print(f"openai  : TP={of.tp} FP={of.fp} FN={of.fn}  "
          f"P={of.precision:.3f} R={of.recall:.3f} F1={of.f1:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
