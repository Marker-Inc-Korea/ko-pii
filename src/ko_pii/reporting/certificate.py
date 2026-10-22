"""Processing record. Source values and document identifiers are opt-in."""
from __future__ import annotations

from datetime import datetime, timezone

from ko_pii.anonymizer import AnonymizationResult
from ko_pii.reporting.explanation import explain


def generate_certificate(
    result: AnonymizationResult,
    document_id: str = "(unspecified)",
    include_review_details: bool = False,
    *,
    include_document_id: bool = False,
    include_replacements: bool = False,
) -> str:
    """Build a value-free record by default, not a legal compliance certificate.

    Opt-in review details, replacement values and document identifiers can expose
    PII. The in-memory result/Vault still contain sensitive data independently.
    """
    report = explain(result)
    parts = ["=" * 60, "개인정보 처리 증명서 (ko-pii)",
             f"생성 일시(UTC): {datetime.now(timezone.utc).isoformat()}",
             f"처리 모드: {report['mode']}", f"총 검출: {report['detection_count']} 건"]
    if include_document_id:
        parts.append(f"문서 식별자: {document_id}")
    if include_review_details or include_document_id or include_replacements:
        parts.append("주의: 명시적으로 요청한 민감한 상세 정보가 포함될 수 있습니다.")
    for action, heading in (("BLOCK", "차단/치환 처리 항목"),
                            ("REVIEW", "검토 대기 항목"), ("ALLOW", "유지 항목")):
        items = [(rec, row) for rec, row in zip(result.detections, report["findings"])
                 if row["action"] == action]
        if not items:
            continue
        parts.append(f"\n[{heading}]")
        for rec, row in items:
            parts.append(f"  - {row['label']} @{row['source_span']} "
                         f"strategy={row['applied_strategy']} status={row['reason']}")
            if action == "REVIEW" and include_review_details:
                parts.append(f"    원문: {rec.detection.text}")
            if action == "BLOCK" and include_replacements and rec.token:
                parts.append(f"    치환값: {rec.token}")
    parts.extend(["", "본 기록은 탐지·처리 내역이며, 미탐지 정보의 부재나 법적 익명성을 보증하지 않습니다.", "=" * 60])
    return "\n".join(parts)
