"""HTML 검토 리포트 — 단일 정적 HTML 파일 (외부 의존성 0).

특징:
- 원본 / 가명본 사이드 바이 사이드
- 카테고리별 색상 오버레이
- 검출 항목 hover → 신뢰도·근거·법조항 툴팁
- 결합 위험도·요약 통계 상단 표시
- 검토 큐 항목별 OK/FP 클릭 마킹 (JS 로컬 다운로드)

핵심 원칙: **단일 파일**, 외부 CSS·JS 없음, 어디서나 열림.
"""
from __future__ import annotations

import html

from ko_pii.anonymizer import AnonymizationResult, DetectionRecord
from ko_pii.core.modes import Action
from ko_pii.core.types import RiskLevel


_CATEGORY_COLORS: dict[str, str] = {
    "RRN": "#d32f2f",
    "FRN": "#d32f2f",
    "PASSPORT": "#c62828",
    "DRIVER_LICENSE": "#c62828",
    "CARD": "#b71c1c",
    "BUSINESS_REG": "#f57c00",
    "CORP_REG": "#f57c00",
    "ACCOUNT": "#e64a19",
    "MEDICAL_INSURANCE": "#ad1457",
    "PRESCRIPTION_ID": "#ad1457",
    "PHONE": "#1976d2",
    "FAX": "#1976d2",
    "EMAIL": "#1565c0",
    "IP": "#0277bd",
    "VEHICLE": "#00838f",
    "POSTAL_CODE": "#00695c",
    "URL": "#9e9e9e",
    "ADDRESS": "#388e3c",
    "PERSON": "#7b1fa2",
    "DOC_ID": "#5d4037",
    "PETITION_ID": "#5d4037",
    "EMPLOYEE_ID": "#6d4c41",
    "PNU": "#558b2f",
    "EDI_DRUG": "#ad1457",
    "COURT_CASE": "#3949ab",
}


def _color_for(label: str) -> str:
    return _CATEGORY_COLORS.get(label, "#616161")


def _annotate_html(
    text: str,
    detections: list[DetectionRecord],
    with_marking: bool = False,
) -> str:
    """텍스트에 검출 span 을 <span class="pii"> 로 감싸 HTML 생성."""
    # detections: list[DetectionRecord]
    sorted_d = sorted(detections, key=lambda r: (r.detection.start, -r.detection.end))
    out: list[str] = []
    cursor = 0
    for r in sorted_d:
        d = r.detection
        if d.start < cursor:
            continue  # overlap (이미 포함됨)
        out.append(html.escape(text[cursor:d.start]))
        risk = RiskLevel(d.risk_level).name
        action = r.action.value
        token_attr = f' data-token="{html.escape(r.token or "")}"' if r.token else ""
        mark_btns = ""
        if with_marking and r.action == Action.REVIEW:
            mark_btns = (
                ' <span class="mark-buttons">'
                '<button class="ok" onclick="mark(this,\'OK\')">✓</button>'
                '<button class="fp" onclick="mark(this,\'FP\')">✗</button>'
                '</span>'
            )
        out.append(
            f'<span class="pii pii-{html.escape(d.label)}" '
            f'style="background:{_color_for(d.label)}22;border-bottom:2px solid {_color_for(d.label)};" '
            f'data-label="{html.escape(d.label)}" '
            f'data-action="{action}" '
            f'data-risk="{risk}" '
            f'data-conf="{d.confidence:.2f}"'
            f'{token_attr} '
            f'title="{html.escape(d.label)} | risk={risk} | conf={d.confidence:.2f} | '
            f'action={action} | {html.escape(d.legal_basis or "")}">'
            f'{html.escape(d.text)}'
            f'</span>{mark_btns}'
        )
        cursor = d.end
    out.append(html.escape(text[cursor:]))
    return "".join(out).replace("\n", "<br>")


_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
       "Noto Sans KR", sans-serif; margin: 0; background: #f5f5f5; color: #212121; }
.header { background: #263238; color: #fff; padding: 16px 24px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 10; }
.header h1 { margin: 0; font-size: 18px; }
.header .meta { font-size: 12px; opacity: 0.7; margin-top: 4px; }
.risk-badge { display:inline-block; padding: 2px 10px; border-radius: 12px;
              font-weight: 600; font-size: 11px; margin-left: 8px; }
.risk-CRITICAL { background:#d32f2f; color:#fff; }
.risk-HIGH { background:#f57c00; color:#fff; }
.risk-MEDIUM { background:#fbc02d; color:#000; }
.risk-LOW { background:#388e3c; color:#fff; }
.risk-INFO { background:#90a4ae; color:#fff; }
.container { display: grid; grid-template-columns: 1fr 1fr;
             gap: 16px; padding: 16px 24px; }
.panel { background: #fff; padding: 16px 20px; border-radius: 6px;
         box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
.panel h2 { margin: 0 0 12px 0; font-size: 14px; color: #555;
            border-bottom: 1px solid #eee; padding-bottom: 8px; }
.text-body { font-family: "Noto Sans Mono", "Consolas", monospace;
             font-size: 13px; line-height: 1.7; white-space: pre-wrap;
             word-break: break-all; }
.pii { padding: 1px 3px; border-radius: 3px; cursor: help; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 12px; padding: 16px 24px; }
.summary-card { background: #fff; padding: 12px; border-radius: 6px;
                box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
.summary-card .label { font-size: 11px; color: #757575; text-transform: uppercase; }
.summary-card .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
.category-list { padding: 16px 24px; }
.cat-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.cat-dot { width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }
.cat-name { font-weight: 500; min-width: 140px; }
.cat-count { color: #555; }
.cat-bar { flex: 1; height: 8px; background: #eee; border-radius: 4px; overflow: hidden; }
.cat-bar-inner { height: 100%; }
.mark-buttons { display: inline-flex; gap: 2px; margin-left: 4px; }
.mark-buttons button { border: 1px solid #ddd; background: #fafafa;
                       padding: 0 6px; cursor: pointer; font-size: 11px; }
.mark-buttons button.ok:hover { background: #c8e6c9; }
.mark-buttons button.fp:hover { background: #ffcdd2; }
.rationale { padding: 16px 24px; }
.rationale ul { margin: 4px 0 0 0; padding-left: 18px; }
.rationale li { font-size: 13px; color: #555; line-height: 1.5; }
"""

_JS = """
let marks = {};
function mark(btn, verdict) {
  const span = btn.parentElement.previousElementSibling;
  const token = span.dataset.token || (span.dataset.label + ':' + span.innerText);
  marks[token] = verdict;
  span.style.outline = verdict === 'OK' ? '2px solid #4caf50' : '2px solid #f44336';
}
function exportMarks() {
  const blob = new Blob([JSON.stringify(marks, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review_marks.json';
  a.click();
}
"""


def generate_html_report(
    original_text: str,
    result: AnonymizationResult,
    *,
    document_id: str = "(unspecified)",
    enable_marking: bool = True,
) -> str:
    s = result.summary
    combined_risk = s.get("combined_risk", "INFO")
    by_label = s.get("by_label", {})
    max_count = max(by_label.values()) if by_label else 1

    # Category bars
    cat_rows = []
    for lbl, n in sorted(by_label.items(), key=lambda x: (-x[1], x[0])):
        color = _color_for(lbl)
        pct = 100 * n / max_count
        cat_rows.append(
            f'<div class="cat-row">'
            f'<div class="cat-dot" style="background:{color}"></div>'
            f'<div class="cat-name">{html.escape(lbl)}</div>'
            f'<div class="cat-count">{n} 건</div>'
            f'<div class="cat-bar"><div class="cat-bar-inner" '
            f'style="background:{color};width:{pct:.1f}%"></div></div>'
            f'</div>'
        )

    rationale_lis = "".join(
        f"<li>{html.escape(r)}</li>" for r in s.get("combined_rationale", [])
    )

    annotated_original = _annotate_html(original_text, result.detections,
                                        with_marking=enable_marking)
    # Anonymized text: show as-is (no annotation needed, it has tokens already)
    annotated_anon = html.escape(result.text).replace("\n", "<br>")

    by_action = s.get("by_action", {})
    by_risk_html = "".join(
        f'<div class="summary-card"><div class="label">{html.escape(k)}</div>'
        f'<div class="value">{v}</div></div>'
        for k, v in by_action.items()
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>ko-pii 검토 리포트: {html.escape(document_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <h1>ko-pii 처리 리포트
    <span class="risk-badge risk-{combined_risk}">{combined_risk}</span>
  </h1>
  <div class="meta">문서: {html.escape(document_id)} · 모드: {html.escape(s.get('mode', '-'))}
    · 전략: {html.escape(s.get('strategy', '-'))} · 총 검출 {s.get('total', 0)} 건</div>
</div>

<div class="summary-grid">
  <div class="summary-card"><div class="label">결합 위험도</div>
    <div class="value">{combined_risk}</div></div>
  {by_risk_html}
</div>

<div class="rationale">
  <strong>판단 근거:</strong>
  <ul>{rationale_lis}</ul>
</div>

<div class="category-list">
  <strong>카테고리별 분포:</strong>
  {''.join(cat_rows)}
</div>

<div class="container">
  <div class="panel">
    <h2>원본 (PII 표시)</h2>
    <div class="text-body">{annotated_original}</div>
  </div>
  <div class="panel">
    <h2>가명화 결과</h2>
    <div class="text-body">{annotated_anon}</div>
  </div>
</div>

{('<div style="padding:16px 24px;"><button onclick="exportMarks()">'
  '검토 마킹 다운로드 (review_marks.json)</button></div>'
  if enable_marking else '')}

<script>{_JS}</script>
</body>
</html>
"""
