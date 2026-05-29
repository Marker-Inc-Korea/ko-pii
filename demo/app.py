"""ko-pii 실시간 비교 데모 — ko-pii vs openai/privacy-filter vs Presidio.

Usage:
    pip install ko-pii gradio
    python demo/app.py

Optional (비교 모델):
    pip install ko-pii[ml]         # openai/privacy-filter
    pip install presidio-analyzer spacy
    python -m spacy download ko_core_news_sm
"""
from __future__ import annotations

import html
import time
from dataclasses import dataclass

import gradio as gr

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.detect import detect_all
from ko_pii.core.types import DetectionResult

# ── 색상 팔레트 (카테고리별) ──────────────────────────────────────
COLORS = {
    "RRN": "#e74c3c", "FRN": "#e74c3c", "PASSPORT": "#e74c3c",
    "DRIVER_LICENSE": "#e74c3c",
    "PERSON": "#3498db", "NATIONALITY": "#1abc9c",
    "PHONE": "#e67e22", "EMAIL": "#e67e22", "FAX": "#e67e22",
    "ADDRESS": "#9b59b6",
    "CARD": "#c0392b", "ACCOUNT": "#c0392b",
    "BUSINESS_REG": "#7f8c8d", "CORP_REG": "#7f8c8d",
    "DT_BIRTH": "#2ecc71", "AGE": "#2ecc71",
    "HEIGHT": "#16a085", "WEIGHT": "#16a085",
    "EDUCATION": "#8e44ad", "MAJOR": "#8e44ad", "POSITION": "#8e44ad",
}
DEFAULT_COLOR = "#95a5a6"


def _color(label: str) -> str:
    return COLORS.get(label, DEFAULT_COLOR)


# ── 하이라이트 HTML 생성 ─────────────────────────────────────────
def _highlight_html(text: str, detections: list[DetectionResult], engine: str) -> str:
    """검출 결과를 HTML 하이라이트로 변환."""
    if not detections:
        escaped = html.escape(text).replace("\n", "<br>")
        return f"<div style='font-family:monospace;white-space:pre-wrap;padding:12px;border:1px solid #ddd;border-radius:8px;background:#fafafa;min-height:100px'>{escaped}<br><br><b>{engine}:</b> 검출 없음</div>"

    # 정렬 (start 기준)
    dets = sorted(detections, key=lambda d: d.start)
    parts: list[str] = []
    last = 0
    for d in dets:
        if d.start > last:
            parts.append(html.escape(text[last:d.start]))
        color = _color(d.label)
        span_text = html.escape(text[d.start:d.end])
        parts.append(
            f'<span style="background:{color}22;border:1px solid {color};'
            f'border-radius:3px;padding:1px 4px" title="{d.label} ({d.confidence:.0%})">'
            f'{span_text}<sup style="color:{color};font-size:0.7em;font-weight:bold">'
            f'{d.label}</sup></span>'
        )
        last = d.end
    if last < len(text):
        parts.append(html.escape(text[last:]))

    body = "".join(parts).replace("\n", "<br>")

    # 요약
    from collections import Counter
    counts = Counter(d.label for d in dets)
    summary = " / ".join(f"{k}:{v}" for k, v in counts.most_common())

    return (
        f"<div style='font-family:monospace;white-space:pre-wrap;padding:12px;"
        f"border:1px solid #ddd;border-radius:8px;background:#fafafa;min-height:100px'>"
        f"{body}<br><br>"
        f"<b>{engine}:</b> {len(dets)}건 ({summary})"
        f"</div>"
    )


# ── 비교 모델 로더 (lazy) ────────────────────────────────────────
_openai_detector = None
_presidio_analyzer = None


def _get_openai():
    global _openai_detector
    if _openai_detector is None:
        try:
            from ko_pii.eval.model_comparison import HFPrivacyDetector
            _openai_detector = HFPrivacyDetector(
                "openai/privacy-filter", backend="torch", device="cpu"
            )
        except Exception:
            return None
    return _openai_detector


def _get_presidio():
    global _presidio_analyzer
    if _presidio_analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            _presidio_analyzer = AnalyzerEngine()
        except Exception:
            return None
    return _presidio_analyzer


def _openai_detect(text: str) -> list[DetectionResult]:
    det = _get_openai()
    if det is None:
        return []
    from ko_pii.eval.model_comparison import OPENAI_TO_KPII
    from ko_pii.core.types import RiskLevel
    results = []
    for s in det.detect(text):
        mapped = OPENAI_TO_KPII.get(s.label, s.label)
        results.append(DetectionResult(
            label=mapped, text=text[s.start:s.end].strip(),
            start=s.start, end=s.end,
            risk_level=RiskLevel.MEDIUM, confidence=0.8,
        ))
    return results


def _presidio_detect(text: str) -> list[DetectionResult]:
    analyzer = _get_presidio()
    if analyzer is None:
        return []
    from ko_pii.core.types import RiskLevel
    PRESIDIO_MAP = {
        "PERSON": "PERSON", "PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL",
        "LOCATION": "ADDRESS", "DATE_TIME": "DT_BIRTH", "URL": "URL",
        "CREDIT_CARD": "CARD", "IP_ADDRESS": "IP",
    }
    results = []
    for r in analyzer.analyze(text=text, language="ko"):
        label = PRESIDIO_MAP.get(r.entity_type, r.entity_type)
        results.append(DetectionResult(
            label=label, text=text[r.start:r.end].strip(),
            start=r.start, end=r.end,
            risk_level=RiskLevel.MEDIUM, confidence=r.score,
        ))
    return results


# ── 메인 처리 ────────────────────────────────────────────────────
def process(text: str, mode: str, show_openai: bool, show_presidio: bool):
    if not text.strip():
        empty = "<div style='padding:12px;color:#999'>텍스트를 입력하세요</div>"
        return empty, empty, empty, ""

    # ko-pii
    t0 = time.time()
    kpii_dets = detect_all(text)
    kpii_time = time.time() - t0
    kpii_html = _highlight_html(text, kpii_dets, f"ko-pii ({kpii_time*1000:.0f}ms)")

    # 가명화
    anon = Anonymizer(mode=ProcessingMode[mode])
    result = anon.process(text)
    anon_text = result.text

    # openai
    if show_openai:
        t0 = time.time()
        openai_dets = _openai_detect(text)
        openai_time = time.time() - t0
        if openai_dets:
            openai_html = _highlight_html(text, openai_dets, f"openai/PF ({openai_time*1000:.0f}ms)")
        else:
            openai_html = "<div style='padding:12px;color:#999'>openai/privacy-filter 미설치 (pip install ko-pii[ml])</div>"
    else:
        openai_html = "<div style='padding:12px;color:#999'>비활성</div>"

    # presidio
    if show_presidio:
        t0 = time.time()
        presidio_dets = _presidio_detect(text)
        presidio_time = time.time() - t0
        if presidio_dets:
            presidio_html = _highlight_html(text, presidio_dets, f"Presidio ({presidio_time*1000:.0f}ms)")
        else:
            presidio_html = "<div style='padding:12px;color:#999'>Presidio 미설치 (pip install presidio-analyzer spacy)</div>"
    else:
        presidio_html = "<div style='padding:12px;color:#999'>비활성</div>"

    return kpii_html, openai_html, presidio_html, anon_text


# ── 예시 텍스트 ──────────────────────────────────────────────────
EXAMPLES = [
    ["""서울특별시 종로구청 민원실 회신문

(수신) 김민지 귀하 (010-1234-5678, mjkim@seoul.go.kr)
(주민등록번호) 880101-2123456
(주소) 서울특별시 강남구 테헤란로 124
(차량번호) 12가1234

처리 담당자는 종로구청 환경위생과 박철수 주임 (02-2148-1234) 이며
회신 기한은 2024년 3월 15일입니다.""", "STRICT", True, True],

    ["""환자명: 홍길동 (1990.03.15생, 34세)
주민번호: 900315-1234567
연락처: 010-9876-5432
주소: 경기도 성남시 분당구 판교로 235 102동 1501호
진단: 고혈압 (I10), 당뇨병 (E11)
처방전번호: RX-2024-0315-001""", "STRICT", True, True],

    ["""거주지국 대한민국 거주지국코드 KR
사업자등록번호 120-81-47521
계좌번호: 110-123-456789 (국민은행)
여권번호 M12345678""", "BALANCED", False, False],
]


# ── Gradio UI ────────────────────────────────────────────────────
with gr.Blocks(title="ko-pii 실시간 PII 비교 데모") as demo:
    gr.Markdown(
        "# ko-pii 실시간 PII 비교 데모\n"
        "한국어 문서의 개인정보를 검출하고 비교합니다. "
        "[GitHub](https://github.com/modak000/ko-pii) · "
        "[PyPI](https://pypi.org/project/ko-pii/)\n\n"
        "> ML 없이 룰+체크섬+사전만으로 동작하는 ko-pii와 "
        "openai/privacy-filter(660M ML), Microsoft Presidio를 나란히 비교합니다."
    )

    with gr.Row():
        with gr.Column(scale=2):
            text_input = gr.Textbox(
                label="텍스트 입력",
                placeholder="개인정보가 포함된 한국어 텍스트를 입력하세요...",
                lines=8,
            )
        with gr.Column(scale=1):
            mode = gr.Radio(
                ["PARANOID", "STRICT", "BALANCED", "PERMISSIVE", "AUDIT"],
                value="STRICT", label="가명화 모드"
            )
            show_openai = gr.Checkbox(label="openai/privacy-filter 비교", value=False)
            show_presidio = gr.Checkbox(label="Microsoft Presidio 비교", value=False)
            btn = gr.Button("검출", variant="primary", size="lg")

    with gr.Row():
        kpii_out = gr.HTML(label="ko-pii (룰 기반)")
    with gr.Row():
        with gr.Column():
            openai_out = gr.HTML(label="openai/privacy-filter")
        with gr.Column():
            presidio_out = gr.HTML(label="Presidio")

    with gr.Accordion("가명화 결과", open=False):
        anon_out = gr.Textbox(label="가명화된 텍스트", lines=8, interactive=False)

    gr.Examples(
        examples=EXAMPLES,
        inputs=[text_input, mode, show_openai, show_presidio],
        label="예시 텍스트",
    )

    btn.click(
        fn=process,
        inputs=[text_input, mode, show_openai, show_presidio],
        outputs=[kpii_out, openai_out, presidio_out, anon_out],
    )
    text_input.submit(
        fn=process,
        inputs=[text_input, mode, show_openai, show_presidio],
        outputs=[kpii_out, openai_out, presidio_out, anon_out],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
