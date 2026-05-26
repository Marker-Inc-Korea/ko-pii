"""Extract Korean text from AI Hub training zips into data/corpus/aihub_*/.

Two datasets (user downloads, 2026-05-21):
  - 71845 (공공 민원 상담)  — each zip has many small JSONs (one consultation each)
  - 569   (행정 문서 기계독해) — each zip has ONE big SQuAD-style JSON with
    63K+ documents inside its `data` array

Output (one .txt per source file):
  data/corpus/aihub_71845/{국립아시아문화전당,중앙행정기관,지방행정기관}.txt
  data/corpus/aihub_569/{multiple_choice,span_extraction,...}.txt
  data/corpus/aihub_combined.txt  — single concatenated file for fp_collector
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
OUT_71845 = DATA / "corpus" / "aihub_71845"
OUT_569 = DATA / "corpus" / "aihub_569"

SRC_71845_TS = (
    DATA
    / "24.공공 민원 상담 LLM 사전학습 및 Instruction Tuning 데이터"
    / "3.개방데이터" / "1.데이터" / "Training" / "01.원천데이터"
)
SRC_569_TS = (
    DATA
    / "016.행정 문서 대상 기계독해 데이터"
    / "01.데이터" / "1.Training" / "원천데이터"
)


def _strip_leading_slash(name: str) -> str:
    return name.lstrip("/").lstrip("\\")


# ---------- 71845 ----------

def docs_from_71845_zip(src_zip: Path) -> Iterator[str]:
    """One zip = many small JSONs. Each JSON = a list with 1 consultation."""
    with zipfile.ZipFile(src_zip) as zf:
        for info in zf.infolist():
            name = _strip_leading_slash(info.filename)
            if info.is_dir() or not name.lower().endswith(".json"):
                continue
            try:
                with zf.open(info) as fh:
                    obj = json.loads(fh.read().decode("utf-8", errors="replace"))
            except Exception:
                continue
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                text = obj[0].get("consulting_content", "")
                if isinstance(text, str) and text.strip():
                    yield text.strip()


# ---------- 569 ----------

def docs_from_569_zip(src_zip: Path) -> Iterator[str]:
    """One zip = ONE big SQuAD-style JSON. data[] has 63K+ records.

    Each record: {doc_id, doc_title, doc_source, paragraphs:[{context, ...}, ...]}
    Yield title + concatenated paragraph contexts per document.
    """
    with zipfile.ZipFile(src_zip) as zf:
        for info in zf.infolist():
            name = _strip_leading_slash(info.filename)
            if info.is_dir() or not name.lower().endswith(".json"):
                continue
            try:
                with zf.open(info) as fh:
                    root = json.loads(fh.read().decode("utf-8", errors="replace"))
            except Exception as e:
                print(f"    parse fail {name}: {e}")
                continue
            data = root.get("data") if isinstance(root, dict) else None
            if not isinstance(data, list):
                continue
            for rec in data:
                if not isinstance(rec, dict):
                    continue
                title = rec.get("doc_title", "")
                paragraphs = rec.get("paragraphs") or []
                parts: list[str] = []
                if isinstance(title, str) and title.strip():
                    parts.append(title.strip())
                for p in paragraphs:
                    if isinstance(p, dict):
                        ctx = p.get("context", "")
                        if isinstance(ctx, str) and ctx.strip():
                            parts.append(ctx.strip())
                if parts:
                    yield "\n\n".join(parts)


# ---------- extraction driver ----------

def extract_to_file(
    docs_iter: Iterator[str],
    out_path: Path,
    *,
    max_docs: int | None,
    label: str,
    progress_every: int = 500,
) -> tuple[int, int]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    total_chars = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for doc in docs_iter:
            out_f.write(doc)
            out_f.write("\n\n")
            n += 1
            total_chars += len(doc)
            if n % progress_every == 0:
                print(f"    {label}: {n:,} docs, {total_chars:,} chars")
            if max_docs and n >= max_docs:
                break
    print(f"  {label} → {out_path.name}: {n:,} docs, {total_chars:,} chars")
    return n, total_chars


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--max-per-source", type=int, default=1000,
        help="Cap docs per source zip (default: 1000 — keeps total ~5-10MB)",
    )
    ap.add_argument(
        "--only", choices=["71845", "569", "both"], default="both",
    )
    args = ap.parse_args()

    if args.only in ("71845", "both"):
        print("=== 71845 (공공 민원 상담) ===")
        OUT_71845.mkdir(parents=True, exist_ok=True)
        for z in sorted(SRC_71845_TS.glob("TS_*.zip")):
            agency = z.stem.replace("TS_", "")
            extract_to_file(
                docs_from_71845_zip(z),
                OUT_71845 / f"{agency}.txt",
                max_docs=args.max_per_source,
                label=z.name,
            )

    if args.only in ("569", "both"):
        print("\n=== 569 (행정문서 기계독해) ===")
        OUT_569.mkdir(parents=True, exist_ok=True)
        for z in sorted(SRC_569_TS.glob("TS_*.zip")):
            task = z.stem.replace("TS_", "")
            extract_to_file(
                docs_from_569_zip(z),
                OUT_569 / f"{task}.txt",
                max_docs=args.max_per_source,
                label=z.name,
            )

    # Combined file
    combined_path = DATA / "corpus" / "aihub_combined.txt"
    parts: list[str] = []
    for sub in (OUT_71845, OUT_569):
        for f in sorted(sub.glob("*.txt")):
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            parts.append(f"=== {f.parent.name}:{f.stem} ===\n{content}")
    combined_path.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"\nCombined: {combined_path}  ({combined_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
