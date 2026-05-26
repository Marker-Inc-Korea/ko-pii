"""부트스트랩 코퍼스 (Wikipedia + korea.kr) 에 두 검출기를 돌려 카테고리별
*탐지 갯수* 만 카운트하는 비교 스크립트.

- 본 코퍼스는 일반 공개 행정/위키 텍스트로, 개별 PII gold span 라벨이 없음.
- 따라서 F1/Precision/Recall 측정 불가 → 단순히 *각 모델이 카테고리별로 몇 개를
  탐지했는지* 만 보고. 카테고리별 분포가 두 모델의 *민감도* 와 *과탐 경향*
  비교의 단서가 됨.

코퍼스 형식: ``=== source:id ===\\n본문\\n`` 단위로 ``=== `` 라인으로 split.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ko_pii.detect import detect_all


def split_documents(text: str) -> list[tuple[str, str]]:
    """=== name === 헤더 단위로 문서 분리.

    Returns list of (header, body).
    """
    docs: list[tuple[str, str]] = []
    current_header = "(미식별)"
    current_body: list[str] = []
    for line in text.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            if current_body:
                docs.append((current_header, "\n".join(current_body).strip()))
                current_body = []
            current_header = line[4:-4]
        else:
            current_body.append(line)
    if current_body:
        docs.append((current_header, "\n".join(current_body).strip()))
    return [(h, b) for h, b in docs if b]


def count_kpii(docs: list[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, body in docs:
        for r in detect_all(body):
            counts[r.label] = counts.get(r.label, 0) + 1
    return counts


def count_openai(docs: list[tuple[str, str]], cache_dir: str, device: str) -> dict[str, int]:
    from ko_pii.eval.model_comparison import HFPrivacyDetector, OPENAI_TO_KPII

    det = HFPrivacyDetector(
        "openai/privacy-filter", backend="onnx",
        device=device, cache_dir=cache_dir,
    )
    print(f"  device: {det.device}", file=sys.stderr)
    counts: dict[str, int] = {}
    for _, body in docs:
        for s in det.detect(body):
            mapped = OPENAI_TO_KPII.get(s.label)
            if not mapped:
                # 매핑 안 되는 라벨도 카운트 (openai 라벨 원래 그대로)
                key = f"(openai){s.label}"
            else:
                key = mapped
            counts[key] = counts.get(key, 0) + 1
    return counts


def render_table(name: str, docs_n: int, bytes_n: int, kpii: dict, openai: dict) -> str:
    all_labels = sorted(set(kpii) | set(openai))
    lines = []
    lines.append(f"## {name}")
    lines.append(f"- 문서 수: {docs_n}, 텍스트: {bytes_n:,} bytes")
    lines.append("")
    lines.append("| 카테고리 | ko-pii 탐지 | openai 탐지 |")
    lines.append("|---|---:|---:|")
    for lbl in all_labels:
        k = kpii.get(lbl, 0)
        o = openai.get(lbl, 0)
        if k == 0 and o == 0:
            continue
        lines.append(f"| {lbl} | {k} | {o} |")
    k_total = sum(kpii.values())
    o_total = sum(openai.values())
    lines.append(f"| **합계** | **{k_total}** | **{o_total}** |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+", help="텍스트 코퍼스 파일")
    p.add_argument("--cache-dir", default="./models")
    p.add_argument("--device", default="cpu")
    p.add_argument("--skip-openai", action="store_true")
    args = p.parse_args()

    sections: list[str] = []
    grand_kpii: dict[str, int] = {}
    grand_openai: dict[str, int] = {}
    total_docs = 0
    total_bytes = 0

    for path in args.paths:
        raw = Path(path).read_text(encoding="utf-8")
        docs = split_documents(raw)
        print(f"\n=== {path} — {len(docs)} docs, {len(raw):,} bytes ===", file=sys.stderr)

        t0 = time.time()
        k = count_kpii(docs)
        print(f"  ko-pii: {time.time()-t0:.1f}s, total={sum(k.values())}", file=sys.stderr)

        if args.skip_openai:
            o = {}
        else:
            t0 = time.time()
            o = count_openai(docs, args.cache_dir, args.device)
            print(f"  openai: {time.time()-t0:.1f}s, total={sum(o.values())}", file=sys.stderr)

        sections.append(render_table(Path(path).name, len(docs), len(raw), k, o))
        for lbl, n in k.items():
            grand_kpii[lbl] = grand_kpii.get(lbl, 0) + n
        for lbl, n in o.items():
            grand_openai[lbl] = grand_openai.get(lbl, 0) + n
        total_docs += len(docs)
        total_bytes += len(raw)

    if len(args.paths) > 1:
        sections.append(render_table("합계 (전체 부트스트랩 코퍼스)",
                                       total_docs, total_bytes,
                                       grand_kpii, grand_openai))

    print("\n".join(sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
