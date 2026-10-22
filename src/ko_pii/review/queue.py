"""검토 큐 (Review Queue) — REVIEW 항목의 영구 저장 + 마킹.

저장 포맷: JSON Lines (``.jsonl``).
각 라인 = 한 항목:

  {"id": "uuid", "doc": "doc.hwpx", "label": "PERSON", "text": "홍길동",
   "span": [42, 45], "confidence": 0.6, "evidence": [...],
   "verdict": null, "verdict_at": null, "verdict_by": null, "verdict_note": ""}

verdict 가 ``null`` 이면 미검토. ``"OK"`` / ``"FP"`` / ``"FN"`` 셋 중 하나.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import dataclass, asdict, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable, Optional

from ko_pii.io_.atomic import write_text_atomic
from ko_pii.structured import loads_json

if TYPE_CHECKING:
    from ko_pii.anonymizer import DetectionRecord
    from ko_pii.core.types import DetectionResult


class Verdict(str, Enum):
    OK = "OK"     # 검출 맞음 (true positive)
    FP = "FP"     # 잘못 검출 (false positive — 사전·룰 보강 필요)
    FN = "FN"     # 진짜였지만 놓침 (사용자 수동 추가)


@dataclass
class ReviewItem:
    id: str
    doc: str
    label: str
    text: str
    span: list[int]
    confidence: float
    evidence: list[str] = field(default_factory=list)
    legal_basis: Optional[str] = None
    verdict: Optional[str] = None
    verdict_at: Optional[str] = None
    verdict_by: Optional[str] = None
    verdict_note: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReviewItem":
        keys = set(cls.__dataclass_fields__)
        if not isinstance(d, dict) or not {"id", "label", "text", "span"} <= d.keys() or not d.keys() <= keys:
            raise ValueError("invalid review item fields")
        for key in ("id", "label", "text"):
            if not isinstance(d[key], str) or not d[key]:
                raise ValueError("invalid review item string")
        for key in ("doc", "verdict_note"):
            if key in d and not isinstance(d[key], str):
                raise ValueError("invalid review metadata")
        for key in ("legal_basis", "verdict_at", "verdict_by"):
            if d.get(key) is not None and not isinstance(d[key], str):
                raise ValueError("invalid review metadata")
        span, confidence, evidence = d["span"], d.get("confidence", 0.0), d.get("evidence", [])
        if (not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span)
                or not 0 <= span[0] < span[1]):
            raise ValueError("invalid review span")
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1 or not math.isfinite(confidence):
            raise ValueError("invalid review confidence")
        if not isinstance(evidence, list) or any(not isinstance(e, str) for e in evidence):
            raise ValueError("invalid review evidence")
        if d.get("verdict") is not None and d["verdict"] not in ("OK", "FP", "FN"):
            raise ValueError("invalid review verdict")
        return cls(
            id=d["id"], doc=d.get("doc", ""), label=d["label"],
            text=d["text"], span=list(d["span"]),
            confidence=float(d.get("confidence", 0.0)),
            evidence=list(d.get("evidence", [])),
            legal_basis=d.get("legal_basis"),
            verdict=d.get("verdict"),
            verdict_at=d.get("verdict_at"),
            verdict_by=d.get("verdict_by"),
            verdict_note=d.get("verdict_note", ""),
        )


class ReviewQueue:
    """파일 기반 검토 큐 (append + rewrite-on-mark)."""

    def __init__(self, path: str):
        self.path = path
        self._items: list[ReviewItem] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if not os.path.exists(self.path):
            self._items = []
            self._loaded = True
            return
        loaded: list[ReviewItem] = []
        ids: set[str] = set()
        with open(self.path, "r", encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = ReviewItem.from_dict(loads_json(line))
                    if item.id in ids:
                        raise ValueError("duplicate review id")
                except (ValueError, TypeError, KeyError):
                    raise ValueError(f"invalid review queue record at line {number}; original file preserved") from None
                ids.add(item.id)
                loaded.append(item)
        self._items = loaded
        self._loaded = True

    def _save(self, items: list[ReviewItem]) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        write_text_atomic(self.path, self._serialize(items))

    @staticmethod
    def _serialize(items: list[ReviewItem]) -> str:
        validated = [ReviewItem.from_dict(item.to_dict()) for item in items]
        if len({item.id for item in validated}) != len(validated):
            raise ValueError("duplicate review id")
        content = "".join(json.dumps(item.to_dict(), ensure_ascii=False, allow_nan=False) + "\n" for item in validated)
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("review items must contain valid Unicode") from None
        return content

    def _append(self, items: list[ReviewItem]) -> None:
        content = self._serialize(items)
        if not items:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if os.path.islink(self.path):
            raise ValueError("review queue must not be a symbolic link")
        prefix = ""
        if os.path.exists(self.path) and os.path.getsize(self.path):
            with open(self.path, "rb") as existing:
                existing.seek(-1, os.SEEK_END)
                if existing.read(1) != b"\n":
                    prefix = "\n"
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(prefix + content)
        except OSError:
            self._loaded = False
            raise
        self._items.extend(items)

    # ─────────────────────── 큐 조작

    def enqueue_detection(
        self, detection: DetectionResult, document: str = ""
    ) -> ReviewItem:
        """``DetectionResult`` 를 검토 큐에 추가."""
        self._load()
        item = ReviewItem(
            id=str(uuid.uuid4()),
            doc=document,
            label=detection.label,
            text=detection.text,
            span=[detection.start, detection.end],
            confidence=detection.confidence,
            evidence=list(detection.evidence),
            legal_basis=detection.legal_basis,
        )
        self._append([item])
        return item

    def enqueue_review_records(
        self, records: Iterable["DetectionRecord"], document: str = ""
    ) -> list[ReviewItem]:
        """``AnonymizationResult.review_items()`` 결과를 일괄 추가."""
        self._load()
        items: list[ReviewItem] = []
        for r in records:
            d = r.detection
            item = ReviewItem(
                id=str(uuid.uuid4()), doc=document, label=d.label, text=d.text,
                span=[d.start, d.end], confidence=d.confidence,
                evidence=list(d.evidence), legal_basis=d.legal_basis,
            )
            items.append(item)
        self._append(items)
        return items

    # ─────────────────────── 조회

    def pending(self) -> list[ReviewItem]:
        self._load()
        return [it for it in self._items if it.verdict is None]

    def all(self) -> list[ReviewItem]:
        self._load()
        return list(self._items)

    def by_id(self, item_id: str) -> Optional[ReviewItem]:
        self._load()
        for it in self._items:
            if it.id == item_id:
                return it
        return None

    def __len__(self) -> int:
        self._load()
        return len(self._items)

    # ─────────────────────── 마킹

    def mark(
        self,
        item_id: str,
        verdict: Verdict,
        *,
        by: Optional[str] = None,
        note: str = "",
    ) -> bool:
        """항목에 verdict 부여. True 면 성공, False 면 ID 없음."""
        if verdict not in (Verdict.OK, Verdict.FP, Verdict.FN):
            raise ValueError("invalid review verdict")
        self._load()
        for index, it in enumerate(self._items):
            if it.id == item_id:
                updated = replace(it, verdict=verdict.value if isinstance(verdict, Verdict) else verdict,
                                  verdict_at=datetime.now(timezone.utc).isoformat(), verdict_by=by, verdict_note=note)
                candidate = list(self._items)
                candidate[index] = updated
                self._save(candidate)
                self._items = candidate
                return True
        return False

    def stats(self) -> dict[str, int]:
        self._load()
        stats = {"total": len(self._items), "pending": 0, "OK": 0, "FP": 0, "FN": 0}
        for it in self._items:
            if it.verdict is None:
                stats["pending"] += 1
            elif it.verdict in stats:
                stats[it.verdict] += 1
        return stats
