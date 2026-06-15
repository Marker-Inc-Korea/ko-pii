"""CLI: ko-pii-classify — 문서 PII 확률 점수 + 하이브리드 검출.

Examples
--------
단일 파일 점수:
    ko-pii-classify input.txt --model models/pii_classifier_v6/final

배치 (jsonl):
    ko-pii-classify --input-jsonl data.jsonl --model models/pii_classifier_v6/final

하이브리드 (룰 + 분류기):
    ko-pii-classify input.txt --model models/pii_classifier_v6/final --hybrid review_flag
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ko-pii-classify",
        description="문서 수준 PII 확률 점수 + 룰/ML 하이브리드 검출.",
    )
    p.add_argument(
        "input",
        nargs="?",
        help="입력 파일 경로 (또는 '-' stdin). --input-jsonl 사용 시 생략.",
    )
    p.add_argument(
        "--input-jsonl",
        type=Path,
        help="JSONL 파일 (각 라인 {'text': ...}). 결과는 stdout JSONL.",
    )
    p.add_argument(
        "--model",
        required=True,
        help="학습된 분류기 디렉토리 (e.g. models/pii_classifier_v6/final).",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="PII 판단 임계값 (default: 0.5).",
    )
    p.add_argument(
        "--hybrid",
        choices=["score", "gated", "review_flag", "union_block"],
        help="ko-pii 룰과 하이브리드. 기본은 분류기만.",
    )
    p.add_argument(
        "--mode",
        default="BALANCED",
        choices=["PARANOID", "STRICT", "BALANCED", "PERMISSIVE", "AUDIT"],
        help="하이브리드 시 ko-pii 모드 (default: BALANCED).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=32,
    )
    p.add_argument(
        "--encoding",
        default="utf-8",
    )
    return p


def _process_single(text: str, args: argparse.Namespace) -> dict[str, Any]:
    from ko_pii.classifier import PIIClassifier

    clf = PIIClassifier.from_pretrained(args.model, threshold=args.threshold)

    if args.hybrid:
        from ko_pii.anonymizer import Anonymizer
        from ko_pii.core.modes import ProcessingMode
        from ko_pii.classifier import HybridAnonymizer, HybridMode

        rule = Anonymizer(mode=ProcessingMode[args.mode])
        h = HybridAnonymizer(
            rule, clf,
            mode=HybridMode(args.hybrid),
            classifier_threshold=args.threshold,
        )
        r = h.process(text)
        return {
            "classifier_score": r.classifier_score,
            "has_pii": r.has_pii,
            "agreement": r.agreement,
            "review_recommended": r.review_recommended,
            "rule_detections": len(r.rule_result.detections),
            "labels": sorted({d.detection.label for d in r.rule_result.detections}),
            "anonymized": r.anonymized,
            "metadata": r.metadata,
        }
    else:
        label, score = clf.predict(text)
        return {"classifier_score": score, "has_pii": bool(label)}


def main() -> None:
    args = _build_parser().parse_args()

    try:  # [classifier] extra 미설치 시 친절한 안내 (mcp/presidio 진입점과 동일 패턴)
        import ko_pii.classifier.predict  # noqa: F401
    except ImportError:
        print("ko-pii classifier 는 추가 의존성이 필요합니다 (torch·transformers·scikit-learn).\n"
              "  pip install ko-pii[classifier]", file=sys.stderr)
        sys.exit(1)

    if args.input_jsonl:
        # 배치 모드
        from ko_pii.classifier import PIIClassifier
        clf = PIIClassifier.from_pretrained(args.model, threshold=args.threshold)
        with args.input_jsonl.open(encoding=args.encoding) as f:
            texts = [json.loads(line) for line in f]
        results = clf.predict_batch([t["text"] for t in texts], batch_size=args.batch_size)
        for src, (label, score) in zip(texts, results):
            out = {**src, "classifier_score": score, "has_pii": bool(label)}
            print(json.dumps(out, ensure_ascii=False))
        return

    if not args.input:
        print("ERROR: input 파일 또는 --input-jsonl 필요", file=sys.stderr)
        sys.exit(2)

    if args.input == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(encoding=args.encoding)

    result = _process_single(text, args)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
