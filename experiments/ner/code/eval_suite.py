#!/usr/bin/env python3
"""평가 스위트 — 한 모델에 대해 두 시각으로 평가.

(a) 단독 seqeval — 모델 라벨셋 기준 토큰분류 성능 (all 모델은 퍼지 서브셋도 별도 산출)
(b) 전체 카테고리 채점 (match_forms_overlap, PML=3) 4모드:
    rule   = ko-pii 룰단독
    ml     = ML 단독 (단일 모델 시나리오 — ML 예측을 데이터셋 gold 라벨공간으로 한정)
    hybrid = ko-pii(결정적 ID 등) + ML(공유 퍼지 10종 교체) — 기존 문서 정의와 동일
    union  = 룰 ∪ ML (양쪽 합집합)

usage: eval_suite.py <model_dir | base-fuzzy>
  base-fuzzy = klue/roberta-large 무학습(헤드 랜덤) + 퍼지 20종 라벨공간
"""
import os, sys, json, re
from pathlib import Path
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
ROOT = Path(__file__).resolve().parents[3]  # 레포 루트 (experiments/ner/code/ 기준)
sys.path.insert(0, str(ROOT / "src"))
import torch
from collections import defaultdict
from transformers import AutoTokenizer, AutoModelForTokenClassification
from seqeval.metrics import f1_score, precision_score, recall_score, classification_report
from ko_pii.eval.kdpii import match_forms_overlap, KDPII_LABEL_MAP
from ko_pii.detect import detect_all

PML = 3
# 하이브리드 정의(기존 문서와 동일): ML이 교체하는 공유 퍼지 10종
FUZZY = {"PERSON", "ADDRESS", "POSITION", "EDUCATION", "MAJOR",
         "NATIONALITY", "AGE", "DT_BIRTH", "HEIGHT", "WEIGHT"}
KD = str(ROOT / "data" / "kdpii")
GEN = str(ROOT / "data")
OUT_DIR = ROOT / "out"

KD_MAP_FUZZY = {
    "PS_NAME": "PERSON", "PS_NICKNAME": "NICKNAME", "LC_ADDRESS": "ADDRESS",
    "LC_PLACE": "PLACE", "LCP_COUNTRY": "NATIONALITY", "CV_POSITION": "POSITION",
    "OG_WORKPLACE": "WORKPLACE", "OG_DEPARTMENT": "DEPARTMENT", "OGG_CLUB": "CLUB",
    "OGG_EDUCATION": "EDUCATION", "FD_MAJOR": "MAJOR", "DT_BIRTH": "DT_BIRTH",
    "QT_AGE": "AGE", "QT_LENGTH": "HEIGHT", "QT_WEIGHT": "WEIGHT",
    "OGG_RELIGION": "RELIGION", "QT_GRADE": "GRADE", "CV_SEX": "SEX",
    "CV_MILITARY_CAMP": "MILITARY", "TM_BLOOD_TYPE": "BLOOD_TYPE",
}
KD_MAP_DET = {
    "QT_CARD_NUMBER": "CARD", "QT_ACCOUNT_NUMBER": "ACCOUNT", "QT_MOBILE": "PHONE",
    "QT_PHONE": "PHONE", "TMI_EMAIL": "EMAIL", "TMI_SITE": "URL",
    "QT_PLATE_NUMBER": "VEHICLE", "QT_ALIEN_NUMBER": "FRN", "QT_IP": "IP",
    "QT_RESIDENT_NUMBER": "RRN", "QT_PASSPORT_NUMBER": "PASSPORT",
    "QT_DRIVER_NUMBER": "DRIVER_LICENSE",
}
KD_MAP_ALL = {**KD_MAP_FUZZY, **KD_MAP_DET}

if len(sys.argv) < 2:
    sys.exit("usage: eval_suite.py <model_dir | base-fuzzy>")
MODEL = sys.argv[1]
if MODEL == "base-fuzzy":
    base = "klue/roberta-large"
    ENT_M = sorted(set(KD_MAP_FUZZY.values()))
    LABELS = ["O"] + [f"{p}-{e}" for e in ENT_M for p in ("B", "I")]
    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForTokenClassification.from_pretrained(
        base, num_labels=len(LABELS),
        id2label={i: l for i, l in enumerate(LABELS)},
        label2id={l: i for i, l in enumerate(LABELS)}).eval().cuda()
    TAG = "klue_base"
else:
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForTokenClassification.from_pretrained(MODEL).eval().cuda()
    ENT_M = sorted({t.split("-", 1)[1] for t in model.config.id2label.values() if t != "O"})
    TAG = os.path.basename(os.path.dirname(MODEL.rstrip("/"))) or "model"
ID2L = model.config.id2label
ENT_SET = set(ENT_M)
print(f"[{TAG}] 라벨 {len(ENT_M)}종: {ENT_M}", flush=True)


# ---------- 데이터 ----------
def kd_docs(split):
    out = []
    for d in json.load(open(f"{KD}/{split}.json", encoding="utf-8")):
        spans = [(p["begin"], p["end"], KD_MAP_ALL[p["label"]])
                 for p in d.get("PII_set", []) if KD_MAP_ALL.get(p["label"]) in ENT_SET]
        out.append({"text": d["sentence"], "spans": spans, "raw": d})
    return out


def gen_docs():
    val_keys = set(json.loads(l)["text"][:90] for l in open(f"{GEN}/generated_eval.jsonl"))
    out = []
    for l in open(f"{GEN}/generated_eval_large.jsonl"):
        d = json.loads(l)
        if d["text"][:90] not in val_keys:
            continue
        spans = []
        for p in d["pii"]:
            if p["type"] not in ENT_SET:
                continue
            for m in re.finditer(re.escape(p["text"]), d["text"]):
                spans.append((m.start(), m.end(), p["type"]))
        out.append({"text": d["text"], "spans": spans, "raw": d})
    return out


# ---------- (a) 단독 seqeval ----------
@torch.no_grad()
def predict_tags(docs):
    P, L = [], []
    for i in range(0, len(docs), 64):
        chunk = docs[i:i + 64]
        enc = tok([d["text"] for d in chunk], truncation=True, max_length=256,
                  padding=True, return_offsets_mapping=True, return_tensors="pt")
        offs = enc.pop("offset_mapping")
        pred = model(**{k: v.cuda() for k, v in enc.items()}).logits.argmax(-1).cpu()
        for j, d in enumerate(chunk):
            pt, lt = [], []
            for (s, e), pid, am in zip(offs[j].tolist(), pred[j].tolist(),
                                       enc["attention_mask"][j].tolist()):
                if am == 0 or s == e:
                    continue
                tag = "O"
                for (bs, be, lab) in d["spans"]:
                    if s < be and bs < e:
                        tag = ("B-" if s <= bs else "I-") + lab
                        break
                lt.append(tag)
                pt.append(ID2L[pid])
            P.append(pt)
            L.append(lt)
    return P, L


def subset(seqs, keep):
    return [[t if t != "O" and t.split("-", 1)[1] in keep else "O" for t in s] for s in seqs]


def seqeval_block(name, P, L):
    print(f"\n==== [단독 seqeval/{TAG}] {name} ====", flush=True)
    print(f"overall F1={f1_score(L, P):.3f} P={precision_score(L, P):.3f} R={recall_score(L, P):.3f}", flush=True)
    print(classification_report(L, P, digits=3, zero_division=0), flush=True)
    return {"f1": f1_score(L, P), "precision": precision_score(L, P), "recall": recall_score(L, P)}


# ---------- (b) 전체 카테고리 채점 ----------
def kopii_pred(text):
    pr = defaultdict(set)
    for r in detect_all(text):
        if r.label == "PERSON" and len(r.text) < PML:
            continue
        pr[r.label].add(r.text)
    return pr


@torch.no_grad()
def ml_pred(text, allowed):
    enc = tok(text, return_offsets_mapping=True, truncation=True, max_length=512,
              return_tensors="pt")
    offs = enc.pop("offset_mapping")[0].tolist()
    pred = model(**{k: v.cuda() for k, v in enc.items()}).logits[0].argmax(-1).tolist()
    out = defaultdict(set)
    cur_lab, cur_s, cur_e = None, None, None

    def flush():
        if cur_lab and cur_lab in allowed:
            v = text[cur_s:cur_e].strip()
            if v and not (cur_lab == "PERSON" and len(v) < PML):
                out[cur_lab].add(v)

    for (s, e), pid in zip(offs, pred):
        if s == e:
            continue
        tag = ID2L[pid]
        if tag == "O":
            flush(); cur_lab = None
            continue
        pos, lab = tag.split("-", 1)
        if pos == "B" or lab != cur_lab:
            flush(); cur_lab, cur_s, cur_e = lab, s, e
        else:
            cur_e = e
    flush()
    return out


def kdpii_gold(d):
    g = defaultdict(set)
    for a in d.get("PII_set", []):
        m = KDPII_LABEL_MAP.get(a.get("label"))
        if not m:
            continue
        f = a.get("form", "")
        if m == "PERSON" and len(f) < PML:
            continue
        if f:
            g[m].add(f)
    return g


def gen_gold(d):
    g = defaultdict(set)
    for p in d["pii"]:
        if p["type"] == "PERSON" and len(p["text"]) < PML:
            continue
        g[p["type"]].add(p["text"])
    return g


def combine(rule, ml, mode):
    if mode == "rule":
        return rule
    if mode == "ml":
        return ml
    pred = defaultdict(set)
    if mode == "hybrid":
        for lab, vs in rule.items():
            if lab not in FUZZY:
                pred[lab] |= vs
        for lab, vs in ml.items():
            if lab in FUZZY:
                pred[lab] |= vs
        return pred
    # union
    for lab, vs in rule.items():
        pred[lab] |= vs
    for lab, vs in ml.items():
        pred[lab] |= vs
    return pred


def score(preds, golds):
    tp = fp = fn = 0
    for pred, g in zip(preds, golds):
        for lab in set(g) | set(pred):
            mp, mg = match_forms_overlap(pred.get(lab, set()), g.get(lab, set()))
            tp += len(mp)
            fp += len(pred.get(lab, set()) - mp)
            fn += len(g.get(lab, set()) - mg)
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    return (2 * P * R / (P + R) if P + R else 0, P, R)


res = {"model": MODEL, "labels": ENT_M}

kd_test = kd_docs("test")
gen_540 = gen_docs()
print(f"KDPII test {len(kd_test)} / 생성 540 {len(gen_540)}", flush=True)

# (a) 단독 seqeval
for name, docs in [("KDPII_test", kd_test), ("generated_540", gen_540)]:
    P, L = predict_tags(docs)
    res[f"seqeval_{name}"] = seqeval_block(name, P, L)
    if len(ENT_M) > 20:  # all 모델: 퍼지 서브셋 별도 (퍼지 모델과 직접 비교용)
        fz = set(KD_MAP_FUZZY.values())
        res[f"seqeval_{name}_fuzzy_subset"] = {
            "f1": f1_score(subset(L, fz), subset(P, fz)),
            "precision": precision_score(subset(L, fz), subset(P, fz)),
            "recall": recall_score(subset(L, fz), subset(P, fz))}
        r = res[f"seqeval_{name}_fuzzy_subset"]
        print(f"  └ 퍼지 20종 서브셋: F1={r['f1']:.3f} P={r['precision']:.3f} R={r['recall']:.3f}", flush=True)

# (b) 전체 카테고리 채점 — ML 예측은 데이터셋 gold 라벨공간으로 한정(공정 비교)
KD_SPACE = set(KDPII_LABEL_MAP.values())
GEN_SPACE = {p["type"] for d in gen_540 for p in d["raw"]["pii"]}
for name, docs, gfn, space in [("KDPII_test", kd_test, kdpii_gold, KD_SPACE),
                               ("generated_540", gen_540, gen_gold, GEN_SPACE)]:
    golds = [gfn(d["raw"]) for d in docs]
    rules = [kopii_pred(d["text"]) for d in docs]
    mls = [ml_pred(d["text"], allowed=ENT_SET & space) for d in docs]
    print(f"\n==== [전체 카테고리 채점/{TAG}] {name} ====", flush=True)
    for mode in ("rule", "ml", "hybrid", "union"):
        f, p, r = score([combine(ru, ml, mode) for ru, ml in zip(rules, mls)], golds)
        res[f"score_{name}_{mode}"] = {"f1": f, "precision": p, "recall": r}
        print(f"  {mode:7s} F1={f:.3f} P={p:.3f} R={r:.3f}", flush=True)

os.makedirs(OUT_DIR, exist_ok=True)
out_path = str(OUT_DIR / f"evalsuite_{TAG}.json")
json.dump(res, open(out_path, "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {out_path}", flush=True)
