"""OpenMed/privacy-filter-multilingual 비교 평가 드라이버.

OpenMed/privacy-filter-multilingual (HF: OpenMed/privacy-filter-multilingual)
는 다국어 PII 검출 모델 (54 카테고리, 217 BIOES tags) 로 *한국어 공식 지원*
('ko' tag).  openai/privacy-filter 와 동일한 ``openai_privacy_filter`` 아키
텍처 — ``trust_remote_code=True`` 필요.

차이점:
  - 라벨 공간 217 (vs openai 33) — FIRSTNAME/LASTNAME/MIDDLENAME, JOBTITLE,
    VRM/VIN, SSN, DATEOFBIRTH 등 한국 PII 일부 커버 가능성 있음.
  - ONNX 미공개 — torch backend 만 가능. CPU 추론은 느림 (~수 시간/벤치마크).

벤치마크:
  1. 200 docs PII 주입       (data/corpus/injected_pii_corpus.jsonl)
  2. KDPII test               (data/kdpii/test.json, 4,891 docs)
  3. KLUE-NER PERSON          (data/klue_ner/klue-ner-v1.1_dev.tsv, 5,000 sents)
  4. 합성 강화 50             (ko_pii.eval.benchmark seed 0)

실행:
  python data/eval_openmed_all.py [--bench injected|kdpii|klue|synth|all]
                                   [--max-docs N]
                                   [--device cpu|cuda]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


FAIR_LABELS = {"PERSON", "EMAIL", "PHONE", "ADDRESS", "DT_BIRTH", "URL", "ACCOUNT"}


def _fair_micro(report) -> tuple[int, int, int, float, float, float]:
    tp = sum(m.tp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fp = sum(m.fp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fn = sum(m.fn for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return tp, fp, fn, p, r, f1


def make_openmed_predict(detector):
    """Adapter — OpenMed Span → DetectionResult (ko-pii eval 호환).

    OpenMed 라벨 (FIRSTNAME, LASTNAME, MIDDLENAME 등 54 카테고리) 을
    ko-pii LABEL 로 매핑.  매핑 안 된 라벨 drop.
    """
    from ko_pii.core.types import DetectionResult, RiskLevel
    from ko_pii.eval.model_comparison import OPENMED_TO_KPII

    def predict(text: str) -> list[DetectionResult]:
        out: list[DetectionResult] = []
        for s in detector.detect(text):
            mapped = OPENMED_TO_KPII.get(s.label)
            if not mapped:
                continue
            out.append(DetectionResult(
                label=mapped,
                text=s.text.strip() if s.text else "",
                start=s.start,
                end=s.end,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
            ))
        return out

    return predict


# -----------------------------------------------------------------------------
# Benchmark runners
# -----------------------------------------------------------------------------


def load_injected(path: str = "data/corpus/injected_pii_corpus.jsonl"):
    from ko_pii.eval.synth import GoldDocument, GoldSpan

    docs = []
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


def load_synth(n: int = 50, seed: int = 0):
    from ko_pii.eval.synth import generate_corpus
    return generate_corpus(n=n, seed=seed)


def run_injected(detector, out_path: Path, max_docs: int | None) -> dict:
    from ko_pii.eval.metrics import format_report, score_corpus

    docs = load_injected()
    if max_docs:
        docs = docs[:max_docs]
    total_spans = sum(len(d.spans) for d in docs)
    print(f"  Loaded {len(docs)} docs, {total_spans} gold spans", file=sys.stderr)

    t0 = time.time()
    report = score_corpus(docs, make_openmed_predict(detector), mode="partial")
    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    m = report.micro()
    fair = _fair_micro(report)
    out_path.write_text(
        f"OpenMed/privacy-filter-multilingual — 200 docs PII 주입{' (sub)' if max_docs else ''}\n"
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
    return {"micro_f1": m.f1, "fair_f1": fair[5]}


def run_synth(detector, out_path: Path, max_docs: int | None) -> dict:
    from ko_pii.eval.metrics import format_report, score_corpus

    docs = load_synth(n=50, seed=0)
    if max_docs:
        docs = docs[:max_docs]
    total_spans = sum(len(d.spans) for d in docs)
    print(f"  Loaded {len(docs)} synth docs, {total_spans} gold spans", file=sys.stderr)

    t0 = time.time()
    report = score_corpus(docs, make_openmed_predict(detector), mode="partial")
    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    m = report.micro()
    fair = _fair_micro(report)
    out_path.write_text(
        f"OpenMed/privacy-filter-multilingual — 합성 강화 (seed 0, 50 docs)\n"
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
    return {"micro_f1": m.f1, "fair_f1": fair[5]}


def run_kdpii(detector, out_path: Path, max_docs: int | None) -> dict:
    from ko_pii.eval.kdpii import (
        evaluate_kdpii,
        format_kdpii_report,
        load_kdpii,
    )

    docs = load_kdpii("data/kdpii/test.json")
    if max_docs:
        docs = docs[:max_docs]
    print(f"  Loaded {len(docs)} KDPII docs", file=sys.stderr)

    predict = make_openmed_predict(detector)

    t0 = time.time()
    report = evaluate_kdpii(docs, detector=predict, person_min_length=3)
    dur = time.time() - t0
    print(f"  Eval: {dur:.1f}s", file=sys.stderr)

    fair_tp = sum(m.tp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fair_fp = sum(m.fp for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fair_fn = sum(m.fn for lab, m in report.per_label.items() if lab in FAIR_LABELS)
    fair_p = fair_tp / (fair_tp + fair_fp) if (fair_tp + fair_fp) else 0.0
    fair_r = fair_tp / (fair_tp + fair_fn) if (fair_tp + fair_fn) else 0.0
    fair_f1 = 2 * fair_p * fair_r / (fair_p + fair_r) if (fair_p + fair_r) else 0.0

    out_path.write_text(
        f"OpenMed/privacy-filter-multilingual — KDPII test ({len(docs)} docs)\n"
        f"  Eval time: {dur:.1f}s\n\n"
        + format_kdpii_report(report)
        + f"\n\n=== Fair Micro (openai 7 라벨만) ===\n"
        f"  TP={fair_tp}  FP={fair_fp}  FN={fair_fn}\n"
        f"  Precision = {fair_p:.3f}\n"
        f"  Recall    = {fair_r:.3f}\n"
        f"  F1        = {fair_f1:.3f}\n",
        encoding="utf-8",
    )
    return {"micro_f1": report.micro_f1, "fair_f1": fair_f1}


def run_klue(detector, out_path: Path, max_docs: int | None) -> dict:
    from ko_pii.context.name_origin import classify_name_origin
    from ko_pii.eval.klue_ner import load_klue_ner

    def is_valid_korean_fullname(text: str) -> bool:
        if len(text) < 3 or len(text) > 5:
            return False
        if not all("가" <= ch <= "힣" for ch in text):
            return False
        return classify_name_origin(text) == "korean"

    sentences = load_klue_ner("data/klue_ner/klue-ner-v1.1_dev.tsv")
    if max_docs:
        sentences = sentences[:max_docs]
    print(f"  Loaded {len(sentences)} KLUE sentences", file=sys.stderr)

    tp = fp = fn = 0
    t0 = time.time()
    for idx, sent in enumerate(sentences):
        if idx and idx % 200 == 0:
            elapsed = time.time() - t0
            print(f"  {idx}/{len(sentences)} ({elapsed:.0f}s, {idx/elapsed:.1f} sent/sec)",
                  file=sys.stderr)
        gold = [
            s for s in sent.spans
            if s.label == "PS" and is_valid_korean_fullname(s.text)
        ]
        raw_pred = detector.detect(sent.text)
        # Filter to FIRSTNAME/LASTNAME/MIDDLENAME → map to PERSON
        from ko_pii.eval.model_comparison import OPENMED_TO_KPII
        pred = []
        for p in raw_pred:
            if OPENMED_TO_KPII.get(p.label) != "PERSON":
                continue
            form = p.text.strip() if p.text else ""
            if not is_valid_korean_fullname(form):
                continue
            pred.append(p)

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
        f"OpenMed/privacy-filter-multilingual — KLUE-NER PS (korean_only=True, 3-5자)\n"
        f"  Sentences: {len(sentences)}, eval time: {dur:.1f}s\n\n"
        f"  TP={tp}  FP={fp}  FN={fn}\n"
        f"  Precision = {p:.3f}\n"
        f"  Recall    = {r:.3f}\n"
        f"  F1        = {f1:.3f}\n",
        encoding="utf-8",
    )
    return {"micro_f1": f1, "fair_f1": f1}


BENCHES = {
    "injected": run_injected,
    "synth": run_synth,
    "kdpii": run_kdpii,
    "klue": run_klue,
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bench", choices=["all", *BENCHES.keys()], default="all")
    p.add_argument("--max-docs", type=int, default=None)
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    p.add_argument("--cache-dir", default="./models")
    p.add_argument("--out-dir", default="data/corpus")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from ko_pii.eval.model_comparison import HFPrivacyDetector

    print(f"Loading OpenMed/privacy-filter-multilingual ({args.device})...", file=sys.stderr)
    det = HFPrivacyDetector(
        "OpenMed/privacy-filter-multilingual",
        backend="torch",
        device=args.device,
        max_seq_len=512,
        cache_dir=args.cache_dir,
    )
    print(f"  Loaded, device={det.device}, labels={len(det.id2label)}", file=sys.stderr)

    benches = list(BENCHES.keys()) if args.bench == "all" else [args.bench]
    summary = {}
    for bench in benches:
        print(f"\n--- {bench} ---", file=sys.stderr)
        suffix = f"_max{args.max_docs}" if args.max_docs else ""
        out_path = out_dir / f"openmed_{bench}{suffix}.txt"
        try:
            result = BENCHES[bench](det, out_path, args.max_docs)
            summary[bench] = result
            print(f"  micro F1: {result['micro_f1']:.3f} | fair F1: {result['fair_f1']:.3f}",
                  file=sys.stderr)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            summary[bench] = {"micro_f1": 0.0, "fair_f1": 0.0, "error": str(e)}

    # Summary
    print("\n\n=== OpenMed 종합 ===")
    print(f"{'벤치마크':<12}{'micro F1':>10}{'fair F1':>10}")
    for bench in benches:
        r = summary.get(bench, {})
        if "error" in r:
            print(f"{bench:<12}    ERROR: {r['error'][:50]}")
        else:
            print(f"{bench:<12}{r.get('micro_f1', 0):>10.3f}{r.get('fair_f1', 0):>10.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
