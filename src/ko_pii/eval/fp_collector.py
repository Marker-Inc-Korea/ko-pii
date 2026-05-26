"""PII 없는 텍스트에서 PERSON 과탐 어휘 자동 수집.

사용 시나리오:
- 비식별된 판결서 / 정부 보도자료 / 뉴스 기사 / 위키백과 등
  → 그 텍스트에 PII 없다는 전제로 우리 검출이 *모두 과탐*
  → 반복 등장 어휘는 일반어 → ``common_words.COMMON_WORDS`` 추가 후보

CLI:
    python -m ko_pii.eval.fp_collector input.txt [--min-freq 2] [--min-length 3]

JSONL 모드 (KDPII 같은 라벨 데이터):
    python -m ko_pii.eval.fp_collector --jsonl kdpii.jsonl --gold-label PS_NAME

출력: ``(빈도, 어휘)`` 형식 — 빈도 내림차순.

자동 추가 시 주의: 일부 어휘는 *진짜 인명* 일 수 있어 사람 검토 후 추가 권장.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ko_pii.detect import detect_all
from ko_pii.dictionaries.common_words import is_common_word


def collect_from_text(
    text: str,
    *,
    label: str = "PERSON",
    min_length: int = 3,
    known_gold: set[str] | None = None,
) -> Counter[str]:
    """텍스트에서 ``label`` 검출 중 ``known_gold`` 와 매칭 안 되는 것 = 과탐 후보."""
    counter: Counter[str] = Counter()
    known = known_gold or set()
    for r in detect_all(text):
        if r.label != label:
            continue
        if len(r.text) < min_length:
            continue
        if is_common_word(r.text):
            continue  # 이미 사전에 있음
        if any(r.text in g or g in r.text for g in known):
            continue  # 정답 매칭
        counter[r.text] += 1
    return counter


def collect_from_jsonl(
    path: str | Path,
    *,
    gold_label: str = "PS_NAME",
    pii_label: str = "PERSON",
    min_length: int = 3,
) -> Counter[str]:
    """JSONL 형식 (query + answer) 에서 ``gold_label`` 제외하고 과탐 수집."""
    counter: Counter[str] = Counter()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            text = d.get("query", "")
            gold = {a["form"] for a in d.get("answer", []) if a["label"] == gold_label}
            # 풀네임 (min_length) 만 정답으로
            gold = {g for g in gold if len(g) >= min_length}
            counter.update(collect_from_text(
                text, label=pii_label, min_length=min_length, known_gold=gold
            ))
    return counter


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ko-pii-fp-collector",
        description="PII 없는 텍스트에서 PERSON 과탐 어휘 자동 수집",
    )
    p.add_argument("path", nargs="?", help="입력 파일 (txt 또는 jsonl)")
    p.add_argument("--jsonl", action="store_true",
                   help="JSONL 모드 (KDPII 같은 라벨링된 데이터)")
    p.add_argument("--gold-label", default="PS_NAME",
                   help="JSONL 의 인명 라벨 (default: PS_NAME)")
    p.add_argument("--pii-label", default="PERSON",
                   help="ko-pii 의 라벨 (default: PERSON)")
    p.add_argument("--min-freq", type=int, default=2,
                   help="최소 반복 횟수 (default: 2)")
    p.add_argument("--min-length", type=int, default=3,
                   help="최소 길이 (default: 3, 풀네임)")
    p.add_argument("--top", type=int, default=100,
                   help="출력할 상위 N개 (default: 100)")
    args = p.parse_args(argv)

    if not args.path:
        p.error("입력 파일 필요")
    path = Path(args.path)
    if not path.exists():
        p.error(f"파일 없음: {path}")

    if args.jsonl:
        counter = collect_from_jsonl(
            path, gold_label=args.gold_label,
            pii_label=args.pii_label, min_length=args.min_length,
        )
    else:
        text = path.read_text(encoding="utf-8")
        counter = collect_from_text(
            text, label=args.pii_label, min_length=args.min_length,
        )

    # min_freq 필터
    filtered = [(t, c) for t, c in counter.items() if c >= args.min_freq]
    filtered.sort(key=lambda x: -x[1])

    print(f"# {path} — 고유 {len(counter)} 종 / 빈도 {args.min_freq}+ "
          f"= {len(filtered)} 종 (총 {sum(c for _, c in filtered)} 건)")
    print(f"# 라벨: {args.pii_label}, 최소 길이: {args.min_length}")
    print()
    print(f"{'빈도':>6}  {'어휘'}")
    print("-" * 40)
    for t, c in filtered[:args.top]:
        print(f"{c:>6}  {t!r}")

    print()
    print("# 일반어 (PERSON 아님) 으로 확인한 어휘만 ``common_words.COMMON_WORDS`` 에 추가 권장.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
