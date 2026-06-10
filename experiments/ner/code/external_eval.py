#!/usr/bin/env python3
"""외부 검증 — Set A(OOD 주입 v2, 체크섬 유효) + Set B(KLUE-NER PS, 인간 라벨).

Set A 구성 6종: rule / ml(퍼지모델) / ml(전체모델) / hybrid(룰+퍼지ML) /
hybrid(룰+전체ML 퍼지부) / verified(전체ML+룰 체크섬 검증).
Set B: rule vs 두 ML 모델의 PERSON (KLUE 관행: 한글 풀네임 gold, partial overlap).

usage: external_eval.py --model-fuzzy <dir> --model-all <dir>
  (인자 생략 시 환경변수 KO_PII_NER_MODEL_FUZZY / KO_PII_NER_MODEL_ALL 사용)
"""
import os, sys, json, re, argparse
from pathlib import Path
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
ROOT = Path(__file__).resolve().parents[3]  # 레포 루트 (experiments/ner/code/ 기준)
sys.path.insert(0, str(ROOT / "src"))
import torch
from collections import defaultdict
from transformers import AutoTokenizer, AutoModelForTokenClassification
from ko_pii.eval.kdpii import match_forms_overlap
from ko_pii.detect import detect_all
from ko_pii.eval.klue_ner import load_klue_ner, evaluate_person
from ko_pii.checksum.luhn import is_valid as luhn_ok
from ko_pii.checksum.business_reg_checksum import is_valid_checksum as biz_ok
from ko_pii.checksum.corp_reg_checksum import is_valid_checksum as corp_ok

PML = 3
FUZZY = {"PERSON", "ADDRESS", "POSITION", "EDUCATION", "MAJOR",
         "NATIONALITY", "AGE", "DT_BIRTH", "HEIGHT", "WEIGHT"}
SETA = str(ROOT / "data" / "corpus" / "external_inject_v2.jsonl")
SETB = str(ROOT / "data" / "klue_ner" / "klue-ner-v1.1_dev.tsv")
OUT_DIR = ROOT / "out"

ap = argparse.ArgumentParser()
ap.add_argument("--model-fuzzy", default=os.environ.get("KO_PII_NER_MODEL_FUZZY"),
                help="퍼지 20종 모델 디렉토리 (기본: $KO_PII_NER_MODEL_FUZZY)")
ap.add_argument("--model-all", default=os.environ.get("KO_PII_NER_MODEL_ALL"),
                help="전체 36종 모델 디렉토리 (기본: $KO_PII_NER_MODEL_ALL)")
args = ap.parse_args()
if not args.model_fuzzy or not args.model_all:
    ap.error("--model-fuzzy / --model-all 필요 (또는 환경변수 KO_PII_NER_MODEL_FUZZY / KO_PII_NER_MODEL_ALL)")
M_FUZZY = args.model_fuzzy
M_ALL = args.model_all


def verify_id(label, span):
    d = re.sub(r"\D", "", span)
    if label == "CARD":
        return 13 <= len(d) <= 19 and d[:1] in "23459" and luhn_ok(d)
    if label == "BUSINESS_REG":
        return len(d) == 10 and biz_ok(d)
    if label == "CORP_REG":
        return len(d) == 13 and corp_ok(d)
    return True


class MLModel:
    def __init__(self, path):
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForTokenClassification.from_pretrained(path).eval().cuda()
        self.id2l = self.model.config.id2label
        self.ents = {t.split("-", 1)[1] for t in self.id2l.values() if t != "O"}

    @torch.no_grad()
    def spans(self, text, allowed=None):
        enc = self.tok(text, return_offsets_mapping=True, truncation=True,
                       max_length=512, return_tensors="pt")
        offs = enc.pop("offset_mapping")[0].tolist()
        pred = self.model(**{k: v.cuda() for k, v in enc.items()}).logits[0].argmax(-1).tolist()
        out, cur = [], None
        for (s, e), pid in zip(offs, pred):
            if s == e:
                continue
            t = self.id2l[pid]
            if t == "O":
                cur = None
                continue
            pos, lab = t.split("-", 1)
            if pos == "B" or not cur or cur[0] != lab:
                out.append([lab, s, e]); cur = (lab,)
            else:
                out[-1][2] = e
        res = []
        for lab, s, e in out:
            if allowed is not None and lab not in allowed:
                continue
            v = text[s:e].strip()
            if v and not (lab == "PERSON" and len(v) < PML):
                res.append((lab, s, e, v))
        return res

    def forms(self, text, allowed):
        out = defaultdict(set)
        for lab, s, e, v in self.spans(text, allowed):
            out[lab].add(v)
        return out

    def free(self):
        del self.model
        torch.cuda.empty_cache()


def kopii_forms(text):
    pr = defaultdict(set)
    for r in detect_all(text):
        if r.label == "PERSON" and len(r.text) < PML:
            continue
        pr[r.label].add(r.text)
    return pr


def score(preds, golds, per_label=False):
    tp = fp = fn = 0
    lab_stat = defaultdict(lambda: [0, 0, 0])
    for pred, g in zip(preds, golds):
        for lab in set(g) | set(pred):
            mp, mg = match_forms_overlap(pred.get(lab, set()), g.get(lab, set()))
            t, f_, n = len(mp), len(pred.get(lab, set()) - mp), len(g.get(lab, set()) - mg)
            tp += t; fp += f_; fn += n
            ls = lab_stat[lab]; ls[0] += t; ls[1] += f_; ls[2] += n
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    F = 2 * P * R / (P + R) if P + R else 0
    if not per_label:
        return F, P, R
    return F, P, R, {k: {"R": v[0] / (v[0] + v[2]) if v[0] + v[2] else 0,
                         "P": v[0] / (v[0] + v[1]) if v[0] + v[1] else 0}
                     for k, v in lab_stat.items()}


def is_fullname(t):
    return 3 <= len(t) <= 5 and all("가" <= c <= "힣" for c in t)


def klue_person_eval(sents, span_fn):
    """evaluate_person 과 동일 관행(풀네임 gold, partial overlap)으로 임의 검출기 평가."""
    tp = fp = fn = 0
    for sent in sents:
        gold = [s for s in sent.spans if s.label == "PS" and is_fullname(s.text)]
        pred = span_fn(sent.text)
        used = set()
        for g in gold:
            hit = -1
            for i, (lab, s, e, v) in enumerate(pred):
                if i in used:
                    continue
                if s < g.end and g.start < e:
                    hit = i; break
            if hit >= 0:
                tp += 1; used.add(hit)
            else:
                fn += 1
        for i, (lab, s, e, v) in enumerate(pred):
            if i not in used and is_fullname(v):
                fp += 1
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    return (2 * P * R / (P + R) if P + R else 0, P, R)


res = {}

# ── Set A ────────────────────────────────────────────────────────
docs = [json.loads(l) for l in open(SETA)]
SPACE = {s["label"] for d in docs for s in d["spans"]}
golds = []
for d in docs:
    g = defaultdict(set)
    for s in d["spans"]:
        if s["label"] == "PERSON" and len(s["text"]) < PML:
            continue
        g[s["label"]].add(s["text"])
    golds.append(g)
print(f"Set A: {len(docs)} docs, 라벨 {sorted(SPACE)}", flush=True)

rules = [kopii_forms(d["text"]) for d in docs]
mf = MLModel(M_FUZZY)
fuzzy_preds = [mf.forms(d["text"], mf.ents & SPACE) for d in docs]
mf.free()
ma = MLModel(M_ALL)
all_preds = [ma.forms(d["text"], ma.ents & SPACE) for d in docs]


def hybrid(rule, ml):
    pred = defaultdict(set)
    for lab, vs in rule.items():
        if lab not in FUZZY:
            pred[lab] |= vs
    for lab, vs in ml.items():
        if lab in FUZZY:
            pred[lab] |= vs
    return pred


def verified(ml):
    return {lab: {v for v in vs if verify_id(lab, v)} for lab, vs in ml.items()}


configs = [
    ("rule", rules),
    ("ml_fuzzy", fuzzy_preds),
    ("ml_all", all_preds),
    ("hybrid_fuzzy", [hybrid(r, m) for r, m in zip(rules, fuzzy_preds)]),
    ("hybrid_all", [hybrid(r, m) for r, m in zip(rules, all_preds)]),
    ("verified_all", [verified(m) for m in all_preds]),
]
print("\n==== Set A (OOD 주입 v2 · 체크섬 유효 · 전체 카테고리) ====", flush=True)
for name, preds in configs:
    F, P, R, labs = score(preds, golds, per_label=True)
    res[f"setA_{name}"] = {"f1": F, "precision": P, "recall": R,
                           "per_label_recall": {k: round(v["R"], 3) for k, v in labs.items()}}
    ids = " ".join(f"{k}:R={labs[k]['R']:.2f}" for k in ("RRN", "CARD", "BUSINESS_REG", "CORP_REG") if k in labs)
    print(f"  {name:13s} F1={F:.3f} P={P:.3f} R={R:.3f}   [{ids}]", flush=True)

# ── Set B (KLUE-NER PS) ─────────────────────────────────────────
sents = load_klue_ner(SETB)
print(f"\n==== Set B (KLUE-NER dev {len(sents)}문장 · 인간 라벨 PS · 풀네임 관행) ====", flush=True)
rep = evaluate_person(sents)
f_rule = 2 * rep.precision * rep.recall / (rep.precision + rep.recall) if rep.precision + rep.recall else 0
res["setB_rule"] = {"f1": f_rule, "precision": rep.precision, "recall": rep.recall}
print(f"  rule          F1={f_rule:.3f} P={rep.precision:.3f} R={rep.recall:.3f}", flush=True)
for name, model in [("ml_all", ma), ("ml_fuzzy", MLModel(M_FUZZY))]:
    F, P, R = klue_person_eval(sents, lambda t, m=model: m.spans(t, {"PERSON"}))
    res[f"setB_{name}"] = {"f1": F, "precision": P, "recall": R}
    print(f"  {name:13s} F1={F:.3f} P={P:.3f} R={R:.3f}", flush=True)

os.makedirs(OUT_DIR, exist_ok=True)
out = str(OUT_DIR / "external_eval.json")
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {out}", flush=True)
