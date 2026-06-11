#!/usr/bin/env python3
"""공공문서 인간 라벨링 샘플 생성 — 가중치 공개 게이트(도메인 일반화 평가)용.

실제 공공 텍스트 4종에서 100문단을 층화 추출하고, ko-pii 룰 검출을 prefill 로
넣어 라벨러가 "수정/추가/삭제"만 하면 되게 한다(처음부터 표시하는 것보다 ~3배 빠름).
prefill 은 룰 출력일 뿐 정답이 아님 — 가이드(GUIDE.md)의 기준으로 교정할 것.

usage: python data/labeling/make_sample.py [--n 100] [--seed 7]
출력: data/labeling/labeling_sample.jsonl
"""
from __future__ import annotations

import argparse, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ko_pii.detect import detect_all

# (소스 파일, 추출 수) — 정책브리핑(실명 공직자 多)·민원·행정·일반
SOURCES = [
    ("corpus/korea_kr.txt", 30),
    ("corpus/aihub_71845/중앙행정기관.txt", 25),
    ("corpus/aihub_71845/지방행정기관.txt", 15),
    ("corpus/aihub_569/span_extraction.txt", 20),
    ("corpus/wikipedia.txt", 10),
]


def blocks(path: Path) -> list[str]:
    sep = "\n\n" if "aihub" in str(path) else "\n"
    out = []
    for b in path.read_text(encoding="utf-8").split(sep):
        b = b.strip()
        if 120 <= len(b) <= 1200:
            out.append(b)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    docs = []
    for rel, k in SOURCES:
        pool = blocks(ROOT / "data" / rel)
        rnd.shuffle(pool)
        for text in pool[:k]:
            docs.append((rel, text))
    rnd.shuffle(docs)
    docs = docs[:args.n]

    out_path = Path(__file__).parent / "labeling_sample.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (src, text) in enumerate(docs):
            prefill = [{"label": r.label, "start": r.start, "end": r.end, "text": r.text}
                       for r in detect_all(text)]
            f.write(json.dumps({"id": f"lab-{i:03d}", "source": src, "text": text,
                                "spans": prefill, "reviewed": False},
                               ensure_ascii=False) + "\n")
    n_spans = sum(len(json.loads(l)["spans"]) for l in open(out_path, encoding="utf-8"))
    print(f"저장: {out_path}  ({len(docs)} docs, prefill {n_spans} spans)")


if __name__ == "__main__":
    main()
