"""KLUE-NER 한국어 자연어 NER 외부 벤치마크 — CLI 진입점.

KLUE benchmark (https://github.com/KLUE-benchmark/KLUE) 데이터를 사용해
*실제 자연어 텍스트* 에서 ko-pii 의 PERSON 검출 정확도를 측정.

KLUE-NER 는 신문기사 기반이라 *공문서가 아님* — 이는 의도된 사용 시나리오
(공문서 정형 양식) 와 다른 *외부 검증* 이다. 결과의 F1 이 합성 공문서
벤치마크보다 낮은 것은 자연스러우며, 룰 기반의 본질적 한계를 반영한다.

데이터 다운로드:
    curl -L -O https://raw.githubusercontent.com/KLUE-benchmark/KLUE/main/\\
         klue_benchmark/klue-ner-v1.1/klue-ner-v1.1_dev.tsv

실행:
    python -m ko_pii.eval.klue_benchmark /path/to/klue-ner-v1.1_dev.tsv
"""
from __future__ import annotations

import argparse

from ko_pii.eval.klue_ner import (
    evaluate_person,
    load_klue_ner,
    sample_errors,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ko-pii-klue-bench",
        description="KLUE-NER 한국어 자연어 NER 외부 벤치마크",
    )
    p.add_argument("path", help="KLUE-NER TSV 파일 경로 (예: klue-ner-v1.1_dev.tsv)")
    p.add_argument("--mode", choices=["partial", "strict"], default="partial")
    p.add_argument("--limit", type=int, default=None,
                   help="평가할 문장 수 (디버그용)")
    p.add_argument("--all-labels", action="store_true",
                   help="모든 PS span 평가 (영문 1자·외래어 포함). 기본은 한글 풀네임만.")
    p.add_argument("--korean-only", action="store_true",
                   help="한국 인명만 평가 (외국인·가공인물 제외) — 본 라이브러리 정책 대상")
    p.add_argument("--show-errors", type=int, default=0,
                   help="FN/FP 샘플 N개씩 출력")
    args = p.parse_args(argv)

    print(f"Loading: {args.path}")
    sentences = load_klue_ner(args.path)
    print(f"Sentences: {len(sentences)}")

    report = evaluate_person(
        sentences,
        mode=args.mode,
        sample_limit=args.limit,
        fullname_only=not args.all_labels,
        korean_only=args.korean_only,
    )
    print()
    print(report.format())

    if args.show_errors > 0:
        print()
        print(f"=== FN 샘플 (ko-pii 가 놓친 이름) ===")
        for sent, names in sample_errors(sentences, "fn", args.show_errors):
            ctx = sent.text[:100]
            print(f"  - {names[0]:<10} ... {ctx}")
        print()
        print(f"=== FP 샘플 (ko-pii 가 잘못 잡은 토큰) ===")
        for sent, names in sample_errors(sentences, "fp", args.show_errors):
            ctx = sent.text[:100]
            print(f"  - {names[0]:<10} ... {ctx}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
