#!/usr/bin/env python3
"""라벨링 웹 UI — labeling_sample.jsonl 검수용 (gradio).

- 문서별로 prefill span 하이라이트 → 틀린 것 삭제 / 빠진 것 추가 / 완료 표시
- 모든 변경은 즉시 파일에 저장(원자적). 최초 실행 시 .backup.jsonl 백업 생성.
- 추가 span 은 문자열 기준(start/end 자동 탐색, 채점은 문자열 기준이라 충분)

usage: python data/labeling/label_ui.py  (gradio 필요)
"""
from __future__ import annotations

import html as _html
import json
import os
import shutil
from pathlib import Path

import gradio as gr

HERE = Path(__file__).resolve().parent
DATA = HERE / "labeling_sample.jsonl"
BACKUP = HERE / "labeling_sample.backup.jsonl"

LABELS = ["PERSON", "PHONE", "EMAIL", "ADDRESS", "POSITION", "WORKPLACE", "DEPARTMENT",
          "RRN", "BUSINESS_REG", "CORP_REG", "ACCOUNT", "CARD", "AGE", "DT_BIRTH",
          "NATIONALITY", "EDUCATION", "MAJOR", "URL", "IP", "VEHICLE", "PASSPORT",
          "DRIVER_LICENSE", "FRN", "POSTAL_CODE", "MEDICAL_INSURANCE", "PRESCRIPTION_ID",
          "HEIGHT", "WEIGHT", "NICKNAME", "PLACE", "CLUB", "RELIGION", "GRADE", "SEX",
          "MILITARY", "BLOOD_TYPE"]

if not BACKUP.exists():
    shutil.copy(DATA, BACKUP)

DOCS = [json.loads(l) for l in open(DATA, encoding="utf-8")]


def save():
    tmp = DATA.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for d in DOCS:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp, DATA)


def span_choices(d):
    return [f"{i}: [{s['label']}] {s['text']}" for i, s in enumerate(d["spans"])]


def highlight(d):
    text, spans = d["text"], d["spans"]
    marks = []
    for s in spans:
        st = s.get("start")
        if st is None:
            st = text.find(s["text"])
        if st >= 0:
            marks.append((st, st + len(s["text"]), s["label"]))
    marks.sort()
    base = ("font-family:monospace;white-space:pre-wrap;padding:14px;border-radius:8px;"
            "background:#fff;color:#111;border:1px solid #ccc;line-height:1.9")
    parts, last = [], 0
    for st, en, lab in marks:
        if st < last:
            continue
        parts.append(_html.escape(text[last:st]))
        parts.append(f'<span style="background:#ffe08a;border:1px solid #d4a017;'
                     f'border-radius:3px;padding:1px 3px">{_html.escape(text[st:en])}'
                     f'<sup style="color:#b8860b;font-size:.7em"> {lab}</sup></span>')
        last = en
    parts.append(_html.escape(text[last:]))
    return f"<div style='{base}'>{''.join(parts)}</div>"


def header(idx):
    d = DOCS[idx]
    done = sum(1 for x in DOCS if x.get("reviewed"))
    flag = "✅ 검수 완료" if d.get("reviewed") else "⬜ 미검수"
    return (f"### 문서 {idx + 1} / {len(DOCS)} — `{d['id']}` ({d['source']})  ·  {flag}\n"
            f"**진행률: {done}/{len(DOCS)} 검수 완료**")


def render(idx):
    d = DOCS[idx]
    return (header(idx), highlight(d),
            gr.update(choices=span_choices(d), value=[]),
            d.get("note", ""))


def goto(idx, delta):
    idx = max(0, min(len(DOCS) - 1, idx + delta))
    return (idx, *render(idx))


def next_unreviewed(idx):
    for j in list(range(idx + 1, len(DOCS))) + list(range(0, idx + 1)):
        if not DOCS[j].get("reviewed"):
            return (j, *render(j))
    return (idx, *render(idx))


def delete_spans(idx, selected):
    d = DOCS[idx]
    kill = {int(s.split(":")[0]) for s in (selected or [])}
    d["spans"] = [s for i, s in enumerate(d["spans"]) if i not in kill]
    save()
    return render(idx)


def add_span(idx, value, label):
    d = DOCS[idx]
    value = (value or "").strip()
    if value:
        if value not in d["text"]:
            gr.Warning(f"본문에 '{value}' 가 없습니다 — 철자를 확인하세요")
        elif any(s["text"] == value and s["label"] == label for s in d["spans"]):
            gr.Warning("이미 같은 라벨로 등록된 값입니다")
        else:
            st = d["text"].find(value)
            d["spans"].append({"label": label, "start": st, "end": st + len(value),
                               "text": value})
            save()
    return (*render(idx), "")


def mark_done(idx, note):
    d = DOCS[idx]
    d["reviewed"] = True
    if (note or "").strip():
        d["note"] = note.strip()
    save()
    return next_unreviewed(idx)


with gr.Blocks(title="ko-pii 라벨링") as app:
    gr.Markdown("# ko-pii 라벨링 검수 — 가중치 공개 게이트\n"
                "노란 하이라이트 = 현재 spans(룰 prefill). **틀린 것 삭제 · 빠진 것 추가 · "
                "끝나면 '완료 → 다음 미검수'**. 저장은 자동입니다. 기준은 `GUIDE.md` 참조 "
                "(조사 제외 · PERSON 은 한글 2자+ 실명만 · 공인 실명도 표기).")
    idx = gr.State(0)
    head = gr.Markdown()
    view = gr.HTML()
    with gr.Row():
        with gr.Column(scale=1):
            sel = gr.CheckboxGroup(label="삭제할 검출 선택", choices=[])
            btn_del = gr.Button("선택 삭제", variant="stop")
        with gr.Column(scale=1):
            new_val = gr.Textbox(label="추가할 문자열 (본문 그대로 복사)",
                                 placeholder="예: 홍길동")
            new_lab = gr.Dropdown(label="라벨", choices=LABELS, value="PERSON")
            btn_add = gr.Button("추가")
    note = gr.Textbox(label="메모 (애매한 판단 등 — 선택)", lines=1)
    with gr.Row():
        btn_prev = gr.Button("◀ 이전")
        btn_next = gr.Button("다음 ▶")
        btn_skip = gr.Button("다음 미검수로")
        btn_done = gr.Button("✅ 이 문서 완료 → 다음 미검수", variant="primary")

    outs = [head, view, sel, note]
    app.load(lambda i: render(i), idx, outs)
    btn_prev.click(lambda i: goto(i, -1), idx, [idx, *outs])
    btn_next.click(lambda i: goto(i, +1), idx, [idx, *outs])
    btn_skip.click(next_unreviewed, idx, [idx, *outs])
    btn_del.click(delete_spans, [idx, sel], outs)
    btn_add.click(add_span, [idx, new_val, new_lab], [*outs, new_val])
    btn_done.click(mark_done, [idx, note], [idx, *outs])

app.launch(server_name="0.0.0.0", server_port=7861)
