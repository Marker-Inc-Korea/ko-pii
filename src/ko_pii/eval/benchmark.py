"""합성 코퍼스 회귀 감지용 벤치마크 — ``python -m ko_pii.eval.benchmark``.

⚠ **이 점수는 실제 정확도가 아니다.** 합성 코퍼스 (`ko_pii.eval.synth`) 는
6 템플릿 (공문서·민원·경찰·소방·인사·결재) 기반의 *좁은* 코퍼스로, 모든 PII
가 필드 라벨 (``성명:``, ``주소:``) anchor 와 함께 등장한다. 검출기가 이런
strict 포맷에 *과적합* 되면 F1 = 1.0 도 가능하다.

용도:
- **회귀 감지** — 새 룰/검출기 추가 시 합성 점수가 떨어지면 기존 케이스
  를 깨뜨렸다는 신호.
- **CI/CD sanity check** — 고정 seed에서 측정한 micro-F1 하한을 명시적으로
  전달해 회귀를 차단한다. 이 하한은 제품 정확도 주장이 아니다.

**실제 정확도 측정은 KDPII 벤치마크 (``ko_pii.eval.kdpii``) 로.**
KDPII 는 53,778 한국어 대화 문서 (Li Fei et al. 2024, IEEE Access) 로
PII 분포가 자연스럽고 anchor 가 모호한 실데이터.
"""
from __future__ import annotations

import argparse

from ko_pii.detect import detect_all
from ko_pii.eval.metrics import format_report, score_corpus
from ko_pii.eval.synth import generate_corpus


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ko-pii-benchmark",
        description="합성 공문서 코퍼스에서 ko-pii 검출 정확도 평가",
    )
    p.add_argument("-n", "--num-docs", type=int, default=50)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mode", choices=["partial", "strict"], default="partial")
    p.add_argument(
        "--min-micro-f1",
        type=float,
        help="exit nonzero when measured micro-F1 is below this floor",
    )
    args = p.parse_args(argv)
    if args.min_micro_f1 is not None and not 0.0 <= args.min_micro_f1 <= 1.0:
        p.error("--min-micro-f1 must be between 0 and 1")

    corpus = generate_corpus(args.num_docs, seed=args.seed)
    report = score_corpus(corpus, detect_all, mode=args.mode)
    print(format_report(report))
    if (
        args.min_micro_f1 is not None
        and report.micro().f1 < args.min_micro_f1
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
