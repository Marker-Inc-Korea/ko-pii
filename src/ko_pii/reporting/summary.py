"""처리 결과 요약 — by_risk / by_action / by_legal_basis."""
from __future__ import annotations

from typing import Iterable

from ko_pii.anonymizer import AnonymizationResult, DetectionRecord
from ko_pii.core.types import RiskLevel


def summarize(result: AnonymizationResult) -> dict:
    """Return the structured summary attached to *result*.

    The summary is built by :class:`Anonymizer`; this function is a thin
    accessor to keep the import path stable.
    """
    return dict(result.summary)


def format_summary_text(result: AnonymizationResult) -> str:
    s = result.summary
    lines: list[str] = []
    lines.append(f"처리 모드: {s.get('mode')}")
    lines.append(f"치환 전략: {s.get('strategy')}")
    lines.append(f"총 검출: {s.get('total')} 건")
    lines.append("")
    lines.append(f"[결합 위험도] {s.get('combined_risk', '—')}")
    for r in s.get("combined_rationale", []):
        lines.append(f"  · {r}")
    if s.get("distinct_identifiers"):
        lines.append(f"  식별자: {', '.join(s['distinct_identifiers'])}")
    if s.get("distinct_quasi_identifiers"):
        lines.append(f"  준식별자: {', '.join(s['distinct_quasi_identifiers'])}")
    if s.get("sensitive_attributes"):
        lines.append(f"  민감속성: {', '.join(s['sensitive_attributes'])}")
    lines.append("")
    lines.append("[조치별 분포]")
    for action, n in sorted(s.get("by_action", {}).items()):
        lines.append(f"  - {action}: {n}")
    lines.append("")
    lines.append("[위험도별 분포]")
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    by_risk = s.get("by_risk", {})
    for name in order:
        if name in by_risk:
            lines.append(f"  - {name}: {by_risk[name]}")
    lines.append("")
    lines.append("[카테고리별 분포]")
    for lbl, n in sorted(
        s.get("by_label", {}).items(), key=lambda x: (-x[1], x[0])
    ):
        lines.append(f"  - {lbl}: {n}")
    lines.append("")
    lines.append("[법적 근거별 분포]")
    for lb, n in sorted(s.get("by_legal_basis", {}).items()):
        lines.append(f"  - {lb}: {n}")
    return "\n".join(lines)


def review_queue(records: Iterable[DetectionRecord]) -> list[dict]:
    """Items that the policy marked for REVIEW — for human inspection."""
    out = []
    for r in records:
        if r.action.value != "REVIEW":
            continue
        d = r.detection
        out.append({
            "label": d.label,
            "text": d.text,
            "span": [d.start, d.end],
            "risk_level": RiskLevel(d.risk_level).name,
            "confidence": d.confidence,
            "evidence": list(d.evidence),
            "legal_basis": d.legal_basis,
        })
    return out
