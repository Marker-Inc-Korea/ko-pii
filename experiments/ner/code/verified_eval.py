#!/usr/bin/env python3
"""3안 측정 — "검출은 ML(전체학습), ID 진위 검증은 룰(체크섬)".

ML단독(ml) vs ML+룰검증(ml_verified)을 동일 매처로 비교한다.
검증 대상: CARD(Luhn+BIN), BUSINESS_REG·CORP_REG(체크섬).
RRN 은 설계상 검증 제외 — 2020-10 뒷자리 무작위화로 체크섬이 신뢰도 신호일 뿐.

드롭 분석: 검증으로 제거된 ML 검출이 gold 였는지(TP 손실) 아닌지(FP 제거)를 분리 집계
→ "합성 gold 의 체크섬 무효 비율" 아티팩트가 점수에 미친 영향을 정량화.
usage: verified_eval.py <model_dir>   (인자 생략 시 환경변수 KO_PII_NER_MODEL 사용)
"""
import os, sys, json, re
from pathlib import Path
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
ROOT = Path(__file__).resolve().parents[3]  # 레포 루트 (experiments/ner/code/ 기준)
sys.path.insert(0, str(ROOT / "src"))
import torch
from collections import defaultdict
from transformers import AutoTokenizer, AutoModelForTokenClassification
from ko_pii.eval.kdpii import match_forms_overlap, KDPII_LABEL_MAP
from ko_pii.checksum.luhn import is_valid as luhn_ok
from ko_pii.checksum.business_reg_checksum import is_valid_checksum as biz_ok
from ko_pii.checksum.corp_reg_checksum import is_valid_checksum as corp_ok

PML = 3
KD = str(ROOT / "data" / "kdpii")
GEN = str(ROOT / "data")
OUT_DIR = ROOT / "out"
MODEL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("KO_PII_NER_MODEL", "")
if not MODEL:
    sys.exit("usage: verified_eval.py <model_dir>   (또는 환경변수 KO_PII_NER_MODEL 설정)")

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForTokenClassification.from_pretrained(MODEL).eval().cuda()
ID2L = model.config.id2label
ENT_SET = {t.split("-", 1)[1] for t in ID2L.values() if t != "O"}


def verify(label, span):
    """룰 체크섬 검증 — 검증기가 없는 라벨은 통과."""
    d = re.sub(r"\D", "", span)
    if label == "CARD":
        return 13 <= len(d) <= 19 and d[:1] in "23459" and luhn_ok(d)
    if label == "BUSINESS_REG":
        return len(d) == 10 and biz_ok(d)
    if label == "CORP_REG":
        return len(d) == 13 and corp_ok(d)
    return True


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
        t = ID2L[pid]
        if t == "O":
            flush(); cur_lab = None
            continue
        pos, lab = t.split("-", 1)
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


kd = json.load(open(f"{KD}/test.json", encoding="utf-8"))
for x in kd:
    x["__text__"] = x["sentence"]
val_keys = set(json.loads(l)["text"][:90] for l in open(f"{GEN}/generated_eval.jsonl"))
gen = [json.loads(l) for l in open(f"{GEN}/generated_eval_large.jsonl")
       if json.loads(l)["text"][:90] in val_keys]
for x in gen:
    x["__text__"] = x["text"]

# gold ID 체크섬 유효율 (해석용)
print("==== gold ID 체크섬 유효율 ====", flush=True)
for name, docs, gfn in [("KDPII_test", kd, kdpii_gold), ("generated_540", gen, gen_gold)]:
    cnt = defaultdict(lambda: [0, 0])
    for d in docs:
        for lab, vs in gfn(d).items():
            if lab in ("CARD", "BUSINESS_REG", "CORP_REG"):
                for v in vs:
                    cnt[lab][0] += verify(lab, v)
                    cnt[lab][1] += 1
    for lab, (ok, n) in sorted(cnt.items()):
        print(f"  [{name}] {lab:14s} {ok}/{n} ({ok/n*100:.0f}%)", flush=True)

KD_SPACE = set(KDPII_LABEL_MAP.values())
res = {"model": MODEL}
for name, docs, gfn, space in [("KDPII_test", kd, kdpii_gold, KD_SPACE),
                               ("generated_540", gen, gen_gold,
                                {p["type"] for d in gen for p in d["pii"]})]:
    golds = [gfn(d) for d in docs]
    mls = [ml_pred(d["__text__"], allowed=ENT_SET & space) for d in docs]
    vers, drop = [], defaultdict(lambda: [0, 0])  # label -> [gold드롭, 비gold드롭]
    for ml, g in zip(mls, golds):
        v = defaultdict(set)
        for lab, vs in ml.items():
            for s in vs:
                if verify(lab, s):
                    v[lab].add(s)
                else:
                    mp, _ = match_forms_overlap({s}, g.get(lab, set()))
                    drop[lab][0 if mp else 1] += 1
        vers.append(v)
    f0, p0, r0 = score(mls, golds)
    f1_, p1, r1 = score(vers, golds)
    print(f"\n==== [{name}] ====", flush=True)
    print(f"  ml단독       F1={f0:.3f} P={p0:.3f} R={r0:.3f}", flush=True)
    print(f"  ml+룰검증(3안) F1={f1_:.3f} P={p1:.3f} R={r1:.3f}   (Δ {f1_-f0:+.3f})", flush=True)
    for lab, (g_, n_) in sorted(drop.items()):
        print(f"    검증 드롭 {lab:14s} gold(TP손실)={g_}  비gold(FP제거)={n_}", flush=True)
    res[name] = {"ml": {"f1": f0, "p": p0, "r": r0},
                 "ml_verified": {"f1": f1_, "p": p1, "r": r1},
                 "drops": {k: {"gold": v[0], "nongold": v[1]} for k, v in drop.items()}}

os.makedirs(OUT_DIR, exist_ok=True)
out = str(OUT_DIR / "verified_klue_all.json")
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {out}", flush=True)
