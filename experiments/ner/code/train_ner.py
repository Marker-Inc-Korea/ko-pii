#!/usr/bin/env python3
"""퍼지 PII 토큰분류 NER 파인튜닝 — ko-pii 하이브리드용.

학습 = KDPII train(대화체) + 생성 행정데이터 1,398(누수 방지: 검증 540 제외)
평가 = KDPII test(대화체) + 생성 검증 540(행정, held-out)
결정적 ID(주민·전화·카드)는 ko-pii(체크섬) 담당 → 퍼지 카테고리만 학습.

usage: train_ner.py --base klue/roberta-large --out OUT [--no-generated] [--trust]
"""
import os, sys, json, argparse, re
from pathlib import Path
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import numpy as np
from datasets import Dataset
from transformers import (AutoTokenizer, AutoModelForTokenClassification,
                          TrainingArguments, Trainer, DataCollatorForTokenClassification)
from seqeval.metrics import f1_score, precision_score, recall_score, classification_report

# KDPII 라벨 → 퍼지 모델 라벨 (결정적 ID 제외)
KD_MAP = {
    "PS_NAME": "PERSON", "PS_NICKNAME": "NICKNAME", "LC_ADDRESS": "ADDRESS",
    "LC_PLACE": "PLACE", "LCP_COUNTRY": "NATIONALITY", "CV_POSITION": "POSITION",
    "OG_WORKPLACE": "WORKPLACE", "OG_DEPARTMENT": "DEPARTMENT", "OGG_CLUB": "CLUB",
    "OGG_EDUCATION": "EDUCATION", "FD_MAJOR": "MAJOR", "DT_BIRTH": "DT_BIRTH",
    "QT_AGE": "AGE", "QT_LENGTH": "HEIGHT", "QT_WEIGHT": "WEIGHT",
    "OGG_RELIGION": "RELIGION", "QT_GRADE": "GRADE", "CV_SEX": "SEX",
    "CV_MILITARY_CAMP": "MILITARY", "TM_BLOOD_TYPE": "BLOOD_TYPE",
}
# 생성셋(ko-pii 라벨) → 퍼지 (공유 카테고리만)
GEN_FUZZY = {"PERSON", "ADDRESS", "POSITION", "EDUCATION", "MAJOR",
             "NATIONALITY", "AGE", "DT_BIRTH", "HEIGHT", "WEIGHT"}
# --all-labels 용: 결정적 ID (기본은 ko-pii 체크섬 담당이라 학습 제외)
KD_DET = {
    "QT_CARD_NUMBER": "CARD", "QT_ACCOUNT_NUMBER": "ACCOUNT", "QT_MOBILE": "PHONE",
    "QT_PHONE": "PHONE", "TMI_EMAIL": "EMAIL", "TMI_SITE": "URL",
    "QT_PLATE_NUMBER": "VEHICLE", "QT_ALIEN_NUMBER": "FRN", "QT_IP": "IP",
    "QT_RESIDENT_NUMBER": "RRN", "QT_PASSPORT_NUMBER": "PASSPORT",
    "QT_DRIVER_NUMBER": "DRIVER_LICENSE",
}
GEN_DET = {"PHONE", "EMAIL", "RRN", "ACCOUNT", "POSTAL_CODE", "URL", "BUSINESS_REG",
           "CARD", "VEHICLE", "MEDICAL_INSURANCE", "IP", "PRESCRIPTION_ID",
           "DRIVER_LICENSE", "CORP_REG", "PASSPORT", "FRN"}

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="klue/roberta-large")
ap.add_argument("--out", required=True)
ap.add_argument("--trust", action="store_true")
ap.add_argument("--no-generated", action="store_true")
ap.add_argument("--epochs", type=float, default=3)
ap.add_argument("--maxlen", type=int, default=256)
ap.add_argument("--bs", type=int, default=32)
ap.add_argument("--bf16", action="store_true")
ap.add_argument("--lr", type=float, default=2e-5)
ap.add_argument("--all-labels", action="store_true",
                help="결정적 ID 포함 전체 카테고리 학습 (퍼지만 학습이 기본)")
args = ap.parse_args()

GEN_TYPES = set(GEN_FUZZY)
if args.all_labels:
    KD_MAP.update(KD_DET)
    GEN_TYPES |= GEN_DET
ENT = sorted(set(KD_MAP.values()) | GEN_TYPES)
LABELS = ["O"] + [f"{p}-{e}" for e in ENT for p in ("B", "I")]
L2I = {l: i for i, l in enumerate(LABELS)}

ROOT = Path(__file__).resolve().parents[3]  # 레포 루트 (experiments/ner/code/ 기준)
KD = str(ROOT / "data" / "kdpii")
GEN = str(ROOT / "data")
os.makedirs(args.out, exist_ok=True)
tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=args.trust)


def kdpii_examples(split):
    out = []
    for d in json.load(open(f"{KD}/{split}.json", encoding="utf-8")):
        spans = [(p["begin"], p["end"], KD_MAP[p["label"]])
                 for p in d.get("PII_set", []) if p["label"] in KD_MAP]
        out.append({"text": d["sentence"], "spans": spans})
    return out


def gen_examples(eval_only):
    """large셋에서 540(검증)만 / 또는 540 제외(학습)."""
    val_keys = set(json.loads(l)["text"][:90] for l in open(f"{GEN}/generated_eval.jsonl"))
    out = []
    for l in open(f"{GEN}/generated_eval_large.jsonl"):
        d = json.loads(l); k = d["text"][:90]; is_val = k in val_keys
        if eval_only != is_val:
            continue
        spans = []
        for p in d["pii"]:
            if p["type"] not in GEN_TYPES:
                continue
            for m in re.finditer(re.escape(p["text"]), d["text"]):
                spans.append((m.start(), m.end(), p["type"]))
        out.append({"text": d["text"], "spans": spans})
    return out


def make_ds(examples):
    """토큰화 + BIO 정렬을 plain Python 으로 수행 → int 컬럼만 Dataset 화."""
    texts = [e["text"] for e in examples]
    sp = [e["spans"] for e in examples]
    ids, masks, labels = [], [], []
    for i in range(0, len(texts), 1000):
        enc = tok(texts[i:i + 1000], truncation=True, max_length=args.maxlen,
                  return_offsets_mapping=True)
        for j, offs in enumerate(enc["offset_mapping"]):
            spans = sp[i + j]
            labs = []
            for (s, e) in offs:
                if s == e:
                    labs.append(-100); continue
                tag = "O"
                for (bs, be, lab) in spans:
                    if s < be and bs < e:
                        tag = ("B-" if s <= bs else "I-") + lab
                        break
                labs.append(L2I[tag])
            ids.append(enc["input_ids"][j])
            masks.append(enc["attention_mask"][j])
            labels.append(labs)
    return Dataset.from_dict({"input_ids": ids, "attention_mask": masks, "labels": labels})


train_ex = kdpii_examples("train")
if not args.no_generated:
    g = gen_examples(eval_only=False); train_ex += g
    print(f"학습: KDPII {len(train_ex)-len(g)} + 생성행정 {len(g)} = {len(train_ex)}", flush=True)
else:
    print(f"학습: KDPII만 {len(train_ex)}", flush=True)

print(f"[{args.base}] 라벨 {len(ENT)}종 · 토큰화...", flush=True)
train_ds = make_ds(train_ex)
val_ds = make_ds(kdpii_examples("valid"))
test_kd = make_ds(kdpii_examples("test"))
test_gen = make_ds(gen_examples(eval_only=True))   # 검증 540 (행정)
print(f"train {len(train_ds)} / valid {len(val_ds)} / KDPII test {len(test_kd)} / 생성 test {len(test_gen)}", flush=True)

model = AutoModelForTokenClassification.from_pretrained(
    args.base, num_labels=len(LABELS), id2label={i: l for l, i in L2I.items()},
    label2id=L2I, ignore_mismatched_sizes=True, trust_remote_code=args.trust)


def decode(preds, labels):
    P, L = [], []
    for pr, lb in zip(np.argmax(preds, axis=2), labels):
        P.append([LABELS[x] for x, l in zip(pr, lb) if l != -100])
        L.append([LABELS[l] for x, l in zip(pr, lb) if l != -100])
    return P, L


def compute(p):
    P, L = decode(p.predictions, p.label_ids)
    return {"f1": f1_score(L, P), "precision": precision_score(L, P), "recall": recall_score(L, P)}


targ = TrainingArguments(
    output_dir=args.out, num_train_epochs=args.epochs,
    per_device_train_batch_size=args.bs, per_device_eval_batch_size=64,
    learning_rate=args.lr, warmup_ratio=0.1, weight_decay=0.01,
    eval_strategy="epoch", save_strategy="epoch", save_total_limit=1,
    load_best_model_at_end=True, metric_for_best_model="f1",
    fp16=not args.bf16, bf16=args.bf16, logging_steps=200, report_to=[])
trainer = Trainer(model=model, args=targ, train_dataset=train_ds, eval_dataset=val_ds,
                  data_collator=DataCollatorForTokenClassification(tok), compute_metrics=compute)
trainer.train()

res = {"base": args.base, "with_generated": not args.no_generated, "all_labels": args.all_labels}
for name, ds in [("KDPII_test", test_kd), ("generated_540", test_gen)]:
    pr = trainer.predict(ds)
    P, L = decode(pr.predictions, pr.label_ids)
    print(f"\n==== [{args.base}] {name} ====", flush=True)
    print(f"overall F1={f1_score(L,P):.3f} P={precision_score(L,P):.3f} R={recall_score(L,P):.3f}", flush=True)
    print(classification_report(L, P, digits=3, zero_division=0), flush=True)
    res[name] = {"f1": f1_score(L, P), "precision": precision_score(L, P), "recall": recall_score(L, P)}

trainer.save_model(args.out + "/final"); tok.save_pretrained(args.out + "/final")
json.dump(res, open(args.out + "/result.json", "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {args.out}/final + result.json", flush=True)
