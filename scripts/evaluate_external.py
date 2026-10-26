"""Opt-in, fixed-protocol external synthetic evaluation; no model or rule tuning."""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import platform
import tempfile
import urllib.request
from pathlib import Path

from ko_pii import ProcessingMode
from ko_pii.eval.domain import evaluate
from ko_pii.eval.external import K_PII_LABELS, load_k_pii_bench

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/external-protocol.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_rows(path: Path, count: int) -> tuple[list[dict], int]:
    seen = set()

    def records():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                identity = row["doc_id"]
                if not isinstance(identity, str) or identity in seen:
                    raise ValueError("invalid or duplicate upstream document ID")
                seen.add(identity)
                yield hashlib.sha256(identity.encode()).hexdigest(), identity, row

    selected = heapq.nsmallest(count, records(), key=lambda x: (x[0], x[1]))
    if len(selected) != count:
        raise ValueError("dataset is smaller than the fixed sample")
    return [row for _, _, row in selected], len(seen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="explicit network opt-in")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; preserve previous measurements")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    args.cache.mkdir(parents=True, exist_ok=True)
    source = args.cache / "k-pii-bench-track-a.jsonl"
    if not source.exists():
        if not args.download:
            parser.error("dataset absent: use --download to fetch the pinned source")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=args.cache, delete=False) as stream:
                temporary = Path(stream.name)
                with urllib.request.urlopen(protocol["url"], timeout=120) as response:
                    size = 0
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > protocol["source_bytes"]:
                            raise ValueError("download exceeds pinned dataset size")
                        stream.write(block)
            if sha256(temporary) != protocol["source_sha256"]:
                raise ValueError("download digest does not match pinned source")
            temporary.replace(source)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if source.stat().st_size != protocol["source_bytes"] or sha256(source) != protocol["source_sha256"]:
        raise ValueError("cached dataset does not match pinned source")
    rows, population = select_rows(source, protocol["sample_size"])
    if population != protocol["population"]:
        raise ValueError("source document count changed")
    with tempfile.TemporaryDirectory() as work:
        subset = Path(work) / "selected.jsonl"
        subset.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                          encoding="utf-8")
        documents, adapter = load_k_pii_bench(subset)
        report = evaluate(documents, labels=[x for x in K_PII_LABELS.values() if x],
                          output_mode=ProcessingMode.STRICT, output_strategy="redact")
    report["external_protocol"] = protocol
    report["protocol_sha256"] = sha256(PROTOCOL)
    report["runner_sha256"] = sha256(Path(__file__))
    report["python"] = platform.python_version()
    report["adapter"] = adapter
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"documents": report["document_count"], "micro": report["micro"],
                      "not_fully_replaced": report["output_evaluation"]["not_fully_replaced"]}))


if __name__ == "__main__":
    main()
