"""Presidio 비교 평가 드라이버 — 4 벤치마크 한 번에.

각 코퍼스에서 ``PresidioDetector(mode="default")`` 와 ``mode="kr_adapt")`` 양쪽을
돌려 micro F1 / 7 라벨 fair-comparison F1 를 측정.

벤치마크:
  1. 200 docs PII 주입       (data/corpus/injected_pii_corpus.jsonl)
  2. KDPII test               (data/kdpii/test.json, 4,891 docs)
  3. KLUE-NER PERSON          (data/klue_ner/klue-ner-v1.1_dev.tsv, 5,000 sents)
  4. 합성 강화 50             (ko_pii.eval.benchmark seed 0)

결과 저장:
  data/corpus/presidio_<corpus>_<mode>.txt

실행:
  python data/eval_presidio_all.py [--bench injected|kdpii|klue|synth|all]
                                   [--mode default|kr_adapt|both]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ko_pii.eval.metrics import format_report, score_corpus
from ko_pii.eval.presidio_compare import PresidioDetector, make_presidio_predict
from ko_pii.eval.synth import GoldDocument, GoldSpan


# openai/PF 와 공정 비교용 7 라벨
FAIR_LABELS = {"PERSON", "EMAIL", "PHONE", "ADDRESS", "DT_BIRTH", "URL", "ACCOUNT"}


def _fair_micro(report) -> tuple[int, int, int, float, float, float]:
    tp = sum(m.tp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fp = sum(m.fp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fn = sum(m.fn for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return tp, fp, fn, p, r, f1


# -----------------------------------------------------------------------------
# 벤치마크 로더
# -----------------------------------------------------------------------------


def load_injected(path: str | Path = "data/corpus/injected_pii_corpus.jsonl") -> list[GoldDocument]:
    docs: list[GoldDocument] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            spans = [
                GoldSpan(label=s["label"], start=s["start"], end=s["end"], text=s["text"])
                for s in d["spans"]
            ]
            docs.append(GoldDocument(text=d["text"], spans=spans))
    return docs


def load_synth(n: int = 50, seed: int = 0) -> list[GoldDocument]:
    """ko_pii.eval.benchmark 의 합성 코퍼스 생성기 사용."""
    from ko_pii.eval.synth import generate_corpus

    return generate_corpus(n=n, seed=seed)


# -----------------------------------------------------------------------------
# Runners
# -----------------------------------------------------------------------------


def run_injected(detector: PresidioDetector, out_path: Path) -> dict:
    docs = load_injected()
    total_spans = sum(len(d.spans) for d in docs)
    print(f"  Loaded {len(docs)} docs, {total_spans} gold spans", file=sys.stderr)

    t0 = time.time()
    report = score_corpus(docs, make_presidio_predict(detector), mode="partial")
    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    m = report.micro()
    fair = _fair_micro(report)
    out_path.write_text(
        f"Presidio ({detector.mode}) — 200 docs PII 주입\n"
        f"  Docs: {len(docs)}, gold spans: {total_spans}, eval time: {dur:.1f}s\n\n"
        + format_report(report)
        + f"\n\n=== Micro (전체 라벨) ===\n"
        f"  TP={m.tp}  FP={m.fp}  FN={m.fn}\n"
        f"  Precision = {m.precision:.3f}\n"
        f"  Recall    = {m.recall:.3f}\n"
        f"  F1        = {m.f1:.3f}\n\n"
        f"=== Fair Micro (openai 7 라벨만) ===\n"
        f"  TP={fair[0]}  FP={fair[1]}  FN={fair[2]}\n"
        f"  Precision = {fair[3]:.3f}\n"
        f"  Recall    = {fair[4]:.3f}\n"
        f"  F1        = {fair[5]:.3f}\n",
        encoding="utf-8",
    )
    return {"micro_f1": m.f1, "fair_f1": fair[5], "tp": m.tp, "fp": m.fp, "fn": m.fn,
            "fair_tp": fair[0], "fair_fp": fair[1], "fair_fn": fair[2]}


def run_synth(detector: PresidioDetector, out_path: Path) -> dict:
    docs = load_synth(n=50, seed=0)
    total_spans = sum(len(d.spans) for d in docs)
    print(f"  Loaded {len(docs)} synth docs, {total_spans} gold spans", file=sys.stderr)

    t0 = time.time()
    report = score_corpus(docs, make_presidio_predict(detector), mode="partial")
    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    m = report.micro()
    fair = _fair_micro(report)
    out_path.write_text(
        f"Presidio ({detector.mode}) — 합성 강화 코퍼스 (seed 0, 50 docs)\n"
        f"  Docs: {len(docs)}, gold spans: {total_spans}, eval time: {dur:.1f}s\n\n"
        + format_report(report)
        + f"\n\n=== Micro (전체 라벨) ===\n"
        f"  TP={m.tp}  FP={m.fp}  FN={m.fn}\n"
        f"  Precision = {m.precision:.3f}\n"
        f"  Recall    = {m.recall:.3f}\n"
        f"  F1        = {m.f1:.3f}\n\n"
        f"=== Fair Micro (openai 7 라벨만) ===\n"
        f"  TP={fair[0]}  FP={fair[1]}  FN={fair[2]}\n"
        f"  Precision = {fair[3]:.3f}\n"
        f"  Recall    = {fair[4]:.3f}\n"
        f"  F1        = {fair[5]:.3f}\n",
        encoding="utf-8",
    )
    return {"micro_f1": m.f1, "fair_f1": fair[5], "tp": m.tp, "fp": m.fp, "fn": m.fn,
            "fair_tp": fair[0], "fair_fp": fair[1], "fair_fn": fair[2]}


def run_kdpii(detector: PresidioDetector, out_path: Path, *, person_min_length: int = 3) -> dict:
    from ko_pii.eval.kdpii import (
        evaluate_kdpii,
        format_kdpii_report,
        load_kdpii,
    )

    docs = load_kdpii("data/kdpii/test.json")
    print(f"  Loaded {len(docs)} KDPII docs", file=sys.stderr)

    predict = make_presidio_predict(detector)

    t0 = time.time()
    report = evaluate_kdpii(docs, detector=predict, person_min_length=person_min_length)
    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    fair_tp = sum(m.tp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fair_fp = sum(m.fp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fair_fn = sum(m.fn for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fair_p = fair_tp / (fair_tp + fair_fp) if (fair_tp + fair_fp) else 0.0
    fair_r = fair_tp / (fair_tp + fair_fn) if (fair_tp + fair_fn) else 0.0
    fair_f1 = 2 * fair_p * fair_r / (fair_p + fair_r) if (fair_p + fair_r) else 0.0

    out_path.write_text(
        f"Presidio ({detector.mode}) — KDPII test ({len(docs)} docs, "
        f"person_min_length={person_min_length})\n"
        f"  Eval time: {dur:.1f}s\n\n"
        + format_kdpii_report(report)
        + f"\n\n=== Fair Micro (openai 7 라벨만) ===\n"
        f"  TP={fair_tp}  FP={fair_fp}  FN={fair_fn}\n"
        f"  Precision = {fair_p:.3f}\n"
        f"  Recall    = {fair_r:.3f}\n"
        f"  F1        = {fair_f1:.3f}\n",
        encoding="utf-8",
    )
    return {"micro_f1": report.micro_f1, "fair_f1": fair_f1,
            "tp": report.micro_tp, "fp": report.micro_fp, "fn": report.micro_fn,
            "fair_tp": fair_tp, "fair_fp": fair_fp, "fair_fn": fair_fn}


def run_klue(detector: PresidioDetector, out_path: Path) -> dict:
    """KLUE-NER PERSON (한글 풀네임 3-5자) 평가 — openai eval 과 동일 로직."""
    from ko_pii.context.name_origin import classify_name_origin
    from ko_pii.eval.klue_ner import load_klue_ner

    def is_valid_korean_fullname(text: str) -> bool:
        if len(text) < 3 or len(text) > 5:
            return False
        if not all("가" <= ch <= "힣" for ch in text):
            return False
        return classify_name_origin(text) == "korean"

    sentences = load_klue_ner("data/klue_ner/klue-ner-v1.1_dev.tsv")
    print(f"  Loaded {len(sentences)} KLUE sentences", file=sys.stderr)

    tp = fp = fn = 0
    t0 = time.time()
    for idx, sent in enumerate(sentences):
        if idx and idx % 500 == 0:
            elapsed = time.time() - t0
            print(f"  {idx}/{len(sentences)} ({elapsed:.0f}s, {idx/elapsed:.1f} sent/sec)",
                  file=sys.stderr)
        gold = [
            s for s in sent.spans
            if s.label == "PS" and is_valid_korean_fullname(s.text)
        ]
        raw_pred = detector.detect(sent.text)
        # PERSON predictions, same filter
        pred = [
            p for p in raw_pred
            if p.label == "PERSON" and is_valid_korean_fullname(p.text.strip() if p.text else "")
        ]
        matched_pred: set[int] = set()
        for g in gold:
            hit = -1
            for i, p in enumerate(pred):
                if i in matched_pred:
                    continue
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

    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    out_path.write_text(
        f"Presidio ({detector.mode}) — KLUE-NER PS (korean_only=True, 3-5자)\n"
        f"  Sentences: {len(sentences)}, eval time: {dur:.1f}s\n\n"
        f"  TP={tp}  FP={fp}  FN={fn}\n"
        f"  Precision = {p:.3f}\n"
        f"  Recall    = {r:.3f}\n"
        f"  F1        = {f1:.3f}\n",
        encoding="utf-8",
    )
    return {"micro_f1": f1, "fair_f1": f1, "tp": tp, "fp": fp, "fn": fn,
            "fair_tp": tp, "fair_fp": fp, "fair_fn": fn}


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------


BENCHES = {
    "injected": run_injected,
    "synth": run_synth,
    "kdpii": run_kdpii,
    "klue": run_klue,
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--bench", choices=["all", *BENCHES.keys()], default="all",
        help="실행할 벤치마크 (기본 all)",
    )
    p.add_argument(
        "--mode", choices=["default", "kr_adapt", "both"], default="both",
        help="Presidio mode 선택",
    )
    p.add_argument("--out-dir", default="data/corpus")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    benches = list(BENCHES.keys()) if args.bench == "all" else [args.bench]
    modes = ["default", "kr_adapt"] if args.mode == "both" else [args.mode]

    summary: dict[str, dict[str, dict]] = {}

    for mode in modes:
        print(f"\n{'='*60}\nPresidio mode={mode}\n{'='*60}", file=sys.stderr)
        det = PresidioDetector(mode=mode)
        summary.setdefault(mode, {})
        for bench in benches:
            print(f"\n--- {bench} ---", file=sys.stderr)
            out_path = out_dir / f"presidio_{bench}_{mode}.txt"
            result = BENCHES[bench](det, out_path)
            summary[mode][bench] = result
            print(
                f"  micro F1: {result['micro_f1']:.3f} | "
                f"fair F1 (7 labels): {result['fair_f1']:.3f}",
                file=sys.stderr,
            )

    # Summary line
    print("\n\n=== 종합 ===")
    print(f"{'벤치마크':<12}", end="")
    for mode in modes:
        print(f"{'Presidio ' + mode:>22}", end="")
    print()
    for bench in benches:
        print(f"{bench:<12}", end="")
        for mode in modes:
            r = summary.get(mode, {}).get(bench)
            if r:
                print(f"  micro {r['micro_f1']:.3f} fair {r['fair_f1']:.3f}".rjust(22), end="")
            else:
                print(f"  ---".rjust(22), end="")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
