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
import os
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewItem":
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
            self._loaded = True
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._items.append(ReviewItem.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue
        self._loaded = True

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            for item in self._items:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False))
                f.write("\n")

    # ─────────────────────── 큐 조작

    def enqueue_detection(self, detection, document: str = "") -> ReviewItem:
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
        self._items.append(item)
        # append-only 로 단일 항목 추가 (성능)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False))
            f.write("\n")
        return item

    def enqueue_review_records(self, records, document: str = "") -> list[ReviewItem]:
        """``AnonymizationResult.review_items()`` 결과를 일괄 추가."""
        self._load()
        items: list[ReviewItem] = []
        # buffer + single open
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            for r in records:
                d = r.detection
                item = ReviewItem(
                    id=str(uuid.uuid4()),
                    doc=document,
                    label=d.label,
                    text=d.text,
                    span=[d.start, d.end],
                    confidence=d.confidence,
                    evidence=list(d.evidence),
                    legal_basis=d.legal_basis,
                )
                self._items.append(item)
                items.append(item)
                f.write(json.dumps(item.to_dict(), ensure_ascii=False))
                f.write("\n")
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
        self._load()
        for it in self._items:
            if it.id == item_id:
                it.verdict = verdict.value if isinstance(verdict, Verdict) else verdict
                it.verdict_at = datetime.now(timezone.utc).isoformat()
                it.verdict_by = by
                it.verdict_note = note
                self._save()  # 전체 재기록 — 마킹은 빈번하지 않음
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
