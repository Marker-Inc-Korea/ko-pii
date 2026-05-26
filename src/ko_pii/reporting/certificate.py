"""처리 증명서 — 감사 추적용 텍스트 보고서.

`AnonymizationResult` 를 받아 다음을 포함한 증명서를 생성한다:
- 처리 일시·모드·전략
- 카테고리별 처리 건수
- 차단된 항목의 토큰 매핑 (원본 노출 없음)
- 검토 대상 큐
- 적용된 법적 근거 목록

Legal basis: 개인정보보호법 제29조 (안전조치의무) — 처리 이력 기록.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ko_pii.anonymizer import AnonymizationResult
from ko_pii.core.types import RiskLevel
from ko_pii.reporting.summary import format_summary_text, review_queue


def generate_certificate(
    result: AnonymizationResult,
    document_id: str = "(unspecified)",
    include_review_details: bool = True,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    parts: list[str] = []
    parts.append("=" * 60)
    parts.append("개인정보 처리 증명서 (ko-pii)")
    parts.append("=" * 60)
    parts.append(f"문서 식별자: {document_id}")
    parts.append(f"생성 일시(UTC): {now}")
    parts.append("")
    parts.append(format_summary_text(result))
    parts.append("")

    blocked = result.blocked_items()
    if blocked:
        parts.append("[차단/치환 처리 항목]")
        for rec in blocked:
            d = rec.detection
            risk = RiskLevel(d.risk_level).name
            token = rec.token or "(no-token)"
            parts.append(
                f"  - {d.label} @[{d.start}:{d.end}] → {token} "
                f"(risk={risk}, conf={d.confidence:.2f})"
            )
        parts.append("")

    review = result.review_items()
    if review and include_review_details:
        parts.append("[검토 대기 항목]")
        for rec in review:
            d = rec.detection
            risk = RiskLevel(d.risk_level).name
            parts.append(
                f"  - {d.label} @[{d.start}:{d.end}] '{d.text}' "
                f"(risk={risk}, conf={d.confidence:.2f})"
            )
        parts.append("")

    parts.append("=" * 60)
    parts.append("본 증명서는 개인정보보호법 제29조에 의거한 처리 기록입니다.")
    parts.append("=" * 60)
    return "\n".join(parts)
