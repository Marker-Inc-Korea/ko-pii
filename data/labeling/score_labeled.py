#!/usr/bin/env python3
"""라벨링 완료본 채점 — 룰(기본) + ML(KO_PII_NER_MODEL 지정 시).

reviewed=true 문서만 채점. 매처는 본 레포 전 평가와 동일(match_forms_overlap, PML=3).
usage: python data/labeling/score_labeled.py [labeling_sample.jsonl]
"""
from __future__ import annotations

import json, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ko_pii.detect import detect_all
from ko_pii.eval.kdpii import match_forms_overlap

PML = 3
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "labeling_sample.jsonl"
docs = [json.loads(l) for l in open(path, encoding="utf-8")]
done = [d for d in docs if d.get("reviewed")]
if not done:
    sys.exit(f"reviewed=true 문서가 없습니다 ({path}) — GUIDE.md 참조")
print(f"채점 대상: {len(done)}/{len(docs)} 문서")


def gold_of(d):
    g = defaultdict(set)
    for s in d["spans"]:
        if s["label"] == "PERSON" and len(s["text"]) < PML:
            continue
        g[s["label"]].add(s["text"])
    return g


def score(preds, golds):
    tp = fp = fn = 0
    for pred, g in zip(preds, golds):
        for lab in set(g) | set(pred):
            mp, mg = match_forms_overlap(pred.get(lab, set()), g.get(lab, set()))
            tp += len(mp); fp += len(pred.get(lab, set()) - mp); fn += len(g.get(lab, set()) - mg)
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    return (2 * P * R / (P + R) if P + R else 0, P, R)


golds = [gold_of(d) for d in done]
rules = []
for d in done:
    pr = defaultdict(set)
    for r in detect_all(d["text"]):
        if r.label == "PERSON" and len(r.text) < PML:
            continue
        pr[r.label].add(r.text)
    rules.append(pr)
F, P, R = score(rules, golds)
print(f"룰단독   F1={F:.3f} P={P:.3f} R={R:.3f}")

model_path = os.environ.get("KO_PII_NER_MODEL")
if model_path:
    from ko_pii.integrations.hf_token_ner import HFTokenNERAdapter
    from ko_pii.integrations.hybrid import DEFAULT_ROLE_SPLIT_LABELS
    ml = HFTokenNERAdapter(model_path)
    mls = []
    for d in done:
        pr = defaultdict(set)
        for r in ml.detect(d["text"]):
            pr[r.label].add(r.text)
        mls.append(pr)
    F, P, R = score(mls, golds)
    print(f"ML단독   F1={F:.3f} P={P:.3f} R={R:.3f}")
    hybs = []
    for ru, m in zip(rules, mls):
        h = defaultdict(set)
        for lab, vs in ru.items():
            if lab not in DEFAULT_ROLE_SPLIT_LABELS:
                h[lab] |= vs
        for lab, vs in m.items():
            if lab in DEFAULT_ROLE_SPLIT_LABELS:
                h[lab] |= vs
        hybs.append(h)
    F, P, R = score(hybs, golds)
    print(f"하이브리드 F1={F:.3f} P={P:.3f} R={R:.3f}   ← 공개 게이트 판정 수치")
else:
    print("(ML 채점: KO_PII_NER_MODEL=<모델경로> 지정 시 출력)")
