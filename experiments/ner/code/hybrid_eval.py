#!/usr/bin/env python3
"""전후 비교 — ko-pii 룰단독 vs ko-pii(결정적)+ML NER(퍼지) 하이브리드.

동일 매처(match_forms_overlap, PML=3). KDPII test + 생성 검증 540.
usage: hybrid_eval.py <model_dir>
"""
import os, sys, json, re
os.environ.setdefault("HF_HOME", "/data1/mk04/.cache/huggingface")
sys.path.insert(0, "/data1/mk04/projects/ko-pii/src")
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from collections import defaultdict
from ko_pii.eval.kdpii import match_forms_overlap, KDPII_LABEL_MAP
from ko_pii.detect import detect_all

MODEL = sys.argv[1]
PML = 3
FUZZY = {"PERSON", "ADDRESS", "POSITION", "EDUCATION", "MAJOR",
         "NATIONALITY", "AGE", "DT_BIRTH", "HEIGHT", "WEIGHT"}

if MODEL == "openai-base":
    # openai/privacy-filter zero-shot (torch GPU) — 퍼지는 PERSON/ADDRESS/DT_BIRTH 만
    from ko_pii.eval.model_comparison import HFPrivacyDetector, OPENAI_TO_KPII
    _hf = HFPrivacyDetector("openai/privacy-filter", backend="torch", device="cuda")

    def ml_spans(text):
        out = defaultdict(set)
        for s in _hf.detect(text):
            lab = OPENAI_TO_KPII.get(s.label)
            if lab in FUZZY:
                v = s.text.strip()
                if lab == "PERSON" and len(v) < PML:
                    continue
                if v:
                    out[lab].add(v)
        return out
else:
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForTokenClassification.from_pretrained(MODEL).eval().cuda()
    ID2L = model.config.id2label

    @torch.no_grad()
    def ml_spans(text):
        enc = tok(text, return_offsets_mapping=True, truncation=True, max_length=512,
                  return_tensors="pt")
        offs = enc.pop("offset_mapping")[0].tolist()
        logits = model(**{k: v.cuda() for k, v in enc.items()}).logits[0]
        pred = logits.argmax(-1).tolist()
        out = defaultdict(set)
        cur_lab, cur_s, cur_e = None, None, None
        def flush():
            if cur_lab and cur_lab in FUZZY:
                out[cur_lab].add(text[cur_s:cur_e])
        for (s, e), pid in zip(offs, pred):
            if s == e:
                continue
            tag = ID2L[pid]
            if tag == "O":
                flush(); cur_lab = None; continue
            pos, lab = tag.split("-", 1)
            if pos == "B" or lab != cur_lab:
                flush(); cur_lab, cur_s, cur_e = lab, s, e
            else:
                cur_e = e
        flush()
        return out


def kopii_pred(text):
    pr = defaultdict(set)
    for r in detect_all(text):
        if r.label == "PERSON" and len(r.text) < PML:
            continue
        pr[r.label].add(r.text)
    return pr


def score(docs, gold_fn, mode):
    tp = fp = fn = 0
    for d in docs:
        g = gold_fn(d)
        kp = kopii_pred(d["__text__"])
        if mode == "rule":
            pred = kp
        else:  # hybrid: ko-pii(결정적) + ML(퍼지)
            pred = defaultdict(set)
            for lab, vs in kp.items():
                if lab not in FUZZY:
                    pred[lab] |= vs
            for lab, vs in ml_spans(d["__text__"]).items():
                pred[lab] |= vs
        for lab in set(g) | set(pred):
            mp, mg = match_forms_overlap(pred.get(lab, set()), g.get(lab, set()))
            tp += len(mp); fp += len(pred.get(lab, set()) - mp); fn += len(g.get(lab, set()) - mg)
    P = tp / (tp + fp) if tp + fp else 0; R = tp / (tp + fn) if tp + fn else 0
    return (2 * P * R / (P + R) if P + R else 0, P, R)


# 데이터
def kdpii_gold(d):
    g = defaultdict(set)
    for a in d.get("PII_set", []):
        m = KDPII_LABEL_MAP.get(a.get("label"))
        if not m: continue
        f = a.get("form", "")
        if m == "PERSON" and len(f) < PML: continue
        if f: g[m].add(f)
    return g

def gen_gold(d):
    g = defaultdict(set)
    for p in d["pii"]:
        if p["type"] == "PERSON" and len(p["text"]) < PML: continue
        g[p["type"]].add(p["text"])
    return g

kd = json.load(open("/data1/mk04/projects/ko-pii/data/kdpii/test.json"))
for x in kd: x["__text__"] = x["sentence"]
gen = [json.loads(l) for l in open("/data1/mk04/projects/ko-pii/data/generated_eval.jsonl")]
for x in gen: x["__text__"] = x["text"]

print("==== 전후 비교 (ko-pii 룰단독 → +ML 하이브리드) ====", flush=True)
for name, docs, gfn in [("KDPII test (대화체)", kd, kdpii_gold), ("생성 540 (행정체)", gen, gen_gold)]:
    rf, rp, rr = score(docs, gfn, "rule")
    hf, hp, hr = score(docs, gfn, "hybrid")
    print(f"\n[{name}]  (전체 카테고리)")
    print(f"  룰단독   F1={rf:.3f} P={rp:.3f} R={rr:.3f}")
    print(f"  하이브리드 F1={hf:.3f} P={hp:.3f} R={hr:.3f}   (Δ {hf-rf:+.3f})")
