"""openai/privacy-filter on synthetic corpus (regression-sanity benchmark).

같은 합성 코퍼스 (`ko_pii.eval.synth.generate_corpus`) 에 대해 ko-pii 와
openai/privacy-filter 양쪽을 측정. score_corpus 가 detector 함수만 받으므로
openai 출력을 DetectionResult 형식으로 wrap.

라벨 매핑: OPENAI_TO_KPII (model_comparison.py). 한국 특화 라벨 (RRN/FRN/
PASSPORT/DRIVER_LICENSE/VEHICLE 등) 은 openai 출력 공간에 없음 → 자동 FN.
이는 모델 성능 부족이 아니라 라벨 스코프 차이 (integration doc 참조).
"""
from __future__ import annotations

import argparse

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.eval.metrics import format_report, score_corpus
from ko_pii.eval.model_comparison import HFPrivacyDetector, OPENAI_TO_KPII
from ko_pii.eval.synth import generate_corpus


def make_openai_predict(detector: HFPrivacyDetector):
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
    p.add_argument("-n", "--num-docs", type=int, default=50)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mode", choices=["partial", "strict"], default="partial")
    p.add_argument("--device", default="cpu")
    p.add_argument("--cache-dir", default="./models")
    args = p.parse_args()

    print(f"Loading openai/privacy-filter...")
    det = HFPrivacyDetector(
        "openai/privacy-filter", backend="onnx", device=args.device,
        cache_dir=args.cache_dir,
    )
    print(f"Device: {det.device}")

    corpus = generate_corpus(args.num_docs, seed=args.seed)
    print(f"Generated {len(corpus)} synthetic docs (seed={args.seed})")

    report = score_corpus(corpus, make_openai_predict(det), mode=args.mode)
    print()
    print("=== openai/privacy-filter on 합성 공문서 코퍼스 ===")
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
