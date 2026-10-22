"""Offline K-PII-Bench JSONL adapter. No dataset download or inferred labels."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any

from ko_pii.eval.domain import (
    LabeledDocument, MAX_DATASET_BYTES, MAX_DOCUMENTS, MAX_DOCUMENT_CHARS,
    MAX_SPANS, _read_json_file,
)
from ko_pii.eval.synth import GoldDocument, GoldSpan
from ko_pii.structured import loads_json

# Broad classes without a one-to-one ko-pii meaning remain explicitly unmapped.
K_PII_LABELS: dict[str, str | None] = {
    "PERSON": "PERSON", "EMAIL_ADDRESS": "EMAIL", "KR_PHONE_NUMBER": "PHONE",
    "KR_RRN": "RRN", "KR_BANK_ACCOUNT": "ACCOUNT", "KR_DRIVER_LICENSE": "DRIVER_LICENSE",
    "KR_PASSPORT": "PASSPORT", "KR_NHIS": "MEDICAL_INSURANCE", "KR_VEHICLE_PLATE": "VEHICLE",
    "KR_LOCATION": "ADDRESS", "CREDIT_CARD": "CARD", "IP_ADDRESS": "IP", "URL": "URL",
    "DATE_OF_BIRTH": "DT_BIRTH", "USERNAME": None, "ORGANIZATION": None,
    "NRP": None, "PERSONAL_ATTRIBUTE": None,
}


def load_k_pii_bench(path: str | Path) -> tuple[list[LabeledDocument], dict[str, Any]]:
    """Validate a bounded local subset; offsets must match optional surface text.

    This uses ko-pii's strict character-span scorer, not the upstream BIO scorer.
    KR_LOCATION -> ADDRESS is a declared alignment, not semantic equivalence.
    """
    raw = _read_json_file(path, MAX_DATASET_BYTES)
    documents = []
    seen_ids: set[str] = set()
    mapped: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    for line_number, line in enumerate(raw.split("\n"), 1):
        if not line.strip():
            continue
        try:
            item = loads_json(line)
            if not isinstance(item, dict):
                raise ValueError
            doc_id, text, entities = item.get("doc_id"), item.get("text"), item.get("entities")
            if not isinstance(doc_id, str) or not doc_id or len(doc_id) > 128 or doc_id in seen_ids:
                raise ValueError
            if not isinstance(text, str) or len(text) > MAX_DOCUMENT_CHARS:
                raise ValueError
            if not isinstance(entities, list) or len(entities) > MAX_SPANS:
                raise ValueError
            spans = []
            seen_spans: set[tuple[str, int, int]] = set()
            for entity in entities:
                if not isinstance(entity, dict):
                    raise ValueError
                label, start, end = entity.get("type"), entity.get("start"), entity.get("end")
                if not isinstance(label, str) or label not in K_PII_LABELS:
                    raise ValueError
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                    raise ValueError
                if "surface" in entity and entity["surface"] != text[start:end]:
                    raise ValueError
                if (label, start, end) in seen_spans:
                    raise ValueError
                seen_spans.add((label, start, end))
                target = K_PII_LABELS[label]
                if target is None:
                    unmapped[label] += 1
                else:
                    mapped[label] += 1
                    spans.append(GoldSpan(target, start, end, text[start:end]))
            seen_ids.add(doc_id)
            safe_id = hashlib.sha256(doc_id.encode("utf-8")).hexdigest()
            documents.append(LabeledDocument(safe_id, GoldDocument(text, spans)))
            if len(documents) > MAX_DOCUMENTS:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"invalid k-pii-bench record at line {line_number}; check schema, label and offsets") from None
    if not documents:
        raise ValueError("dataset must contain at least one document")
    metadata = {
        "format": "k-pii-bench-jsonl", "adapter_version": 1,
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "label_map": dict(K_PII_LABELS), "mapped_spans": dict(mapped),
        "unmapped_spans": dict(unmapped), "unmapped_span_count": sum(unmapped.values()),
        "warning": "Mapped-label strict-span evaluation only; not the official upstream score or a full-coverage claim.",
    }
    return documents, metadata
