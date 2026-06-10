#!/usr/bin/env python3
"""Gemma-4 (E2B/E4B) 텍스트 타워 + 커스텀 토큰분류 헤드 — PII NER 파인튜닝.

transformers 5.10.2 에 Gemma4ForTokenClassification 이 없어 직접 구성:
Gemma4ForConditionalGeneration(멀티모달)에서 텍스트 타워만 추출 → dropout+linear 헤드.
비전/오디오 타워는 메모리 절약 위해 제거. 데이터·라벨·평가는 train_ner.py 와 동일
(전체 36종 = klue_all 과 직접 비교 가능).

usage: gemma4_train_ner.py --base <path|hf_id> --out OUT [--smoke] [--lr 5e-5] ...
"""
import os, sys, json, argparse, re
os.environ.setdefault("HF_HOME", "/data1/mk04/.cache/huggingface")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import numpy as np
import torch
import torch.nn as nn
from datasets import Dataset
from transformers import (AutoTokenizer, AutoConfig, AutoModel,
                          TrainingArguments, Trainer, DataCollatorForTokenClassification)
from transformers.modeling_outputs import TokenClassifierOutput
from seqeval.metrics import f1_score, precision_score, recall_score, classification_report

KD_MAP = {
    "PS_NAME": "PERSON", "PS_NICKNAME": "NICKNAME", "LC_ADDRESS": "ADDRESS",
    "LC_PLACE": "PLACE", "LCP_COUNTRY": "NATIONALITY", "CV_POSITION": "POSITION",
    "OG_WORKPLACE": "WORKPLACE", "OG_DEPARTMENT": "DEPARTMENT", "OGG_CLUB": "CLUB",
    "OGG_EDUCATION": "EDUCATION", "FD_MAJOR": "MAJOR", "DT_BIRTH": "DT_BIRTH",
    "QT_AGE": "AGE", "QT_LENGTH": "HEIGHT", "QT_WEIGHT": "WEIGHT",
    "OGG_RELIGION": "RELIGION", "QT_GRADE": "GRADE", "CV_SEX": "SEX",
    "CV_MILITARY_CAMP": "MILITARY", "TM_BLOOD_TYPE": "BLOOD_TYPE",
    # 결정적 ID (전체학습)
    "QT_CARD_NUMBER": "CARD", "QT_ACCOUNT_NUMBER": "ACCOUNT", "QT_MOBILE": "PHONE",
    "QT_PHONE": "PHONE", "TMI_EMAIL": "EMAIL", "TMI_SITE": "URL",
    "QT_PLATE_NUMBER": "VEHICLE", "QT_ALIEN_NUMBER": "FRN", "QT_IP": "IP",
    "QT_RESIDENT_NUMBER": "RRN", "QT_PASSPORT_NUMBER": "PASSPORT",
    "QT_DRIVER_NUMBER": "DRIVER_LICENSE",
}
GEN_TYPES = {"PERSON", "ADDRESS", "POSITION", "EDUCATION", "MAJOR", "NATIONALITY",
             "AGE", "DT_BIRTH", "HEIGHT", "WEIGHT", "PHONE", "EMAIL", "RRN",
             "ACCOUNT", "POSTAL_CODE", "URL", "BUSINESS_REG", "CARD", "VEHICLE",
             "MEDICAL_INSURANCE", "IP", "PRESCRIPTION_ID", "DRIVER_LICENSE",
             "CORP_REG", "PASSPORT", "FRN"}
ENT = sorted(set(KD_MAP.values()) | GEN_TYPES)
LABELS = ["O"] + [f"{p}-{e}" for e in ENT for p in ("B", "I")]
L2I = {l: i for i, l in enumerate(LABELS)}

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--epochs", type=float, default=3)
ap.add_argument("--maxlen", type=int, default=256)
ap.add_argument("--bs", type=int, default=8)
ap.add_argument("--accum", type=int, default=4)
ap.add_argument("--lr", type=float, default=5e-5)
ap.add_argument("--smoke", action="store_true", help="CPU 로딩·forward 스모크만")
args = ap.parse_args()

KD = "/data1/mk04/projects/ko-pii/data/kdpii"
GEN = "/data1/mk04/projects/ko-pii/data"


# ── 모델: 텍스트 타워 + 분류 헤드 ──────────────────────────
class Gemma4TokenClassifier(nn.Module):
    def __init__(self, base, num_labels):
        super().__init__()
        cfg = AutoConfig.from_pretrained(base)
        # 멀티모달 전체 로드 후 텍스트 타워만 추출 (가중치 키 매핑 안전)
        full = AutoModel.from_pretrained(base, dtype=torch.bfloat16)
        print(f"  로드 클래스: {type(full).__name__}", flush=True)
        text = None
        for name in ("language_model", "text_model"):
            if hasattr(full, name):
                text = getattr(full, name); break
            if hasattr(full, "model") and hasattr(full.model, name):
                text = getattr(full.model, name); break
        if text is None:
            raise RuntimeError(f"텍스트 타워 못 찾음 — 최상위 모듈: {[n for n,_ in full.named_children()]}")
        print(f"  텍스트 타워: {type(text).__name__}", flush=True)
        self.backbone = text
        hidden = getattr(cfg, "text_config", cfg).hidden_size
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(hidden, num_labels)  # fp32 헤드
        self.num_labels = num_labels
        self.config = getattr(cfg, "text_config", cfg)   # Trainer 호환
        self.config.num_labels = num_labels
        del full  # 비전/오디오 타워 해제

    def gradient_checkpointing_enable(self, **kw):
        self.backbone.gradient_checkpointing_enable(**kw)

    def forward(self, input_ids=None, attention_mask=None, labels=None, **kw):
        h = self.backbone(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        logits = self.classifier(self.dropout(h.float()))
        loss = None
        if labels is not None:
            loss = nn.CrossEntropyLoss()(logits.view(-1, self.num_labels), labels.view(-1))
        return TokenClassifierOutput(loss=loss, logits=logits)


# ── 데이터 (train_ner.py 동일) ─────────────────────────────
tok = AutoTokenizer.from_pretrained(args.base)


def kdpii_examples(split):
    out = []
    for d in json.load(open(f"{KD}/{split}.json", encoding="utf-8")):
        spans = [(p["begin"], p["end"], KD_MAP[p["label"]])
                 for p in d.get("PII_set", []) if p["label"] in KD_MAP]
        out.append({"text": d["sentence"], "spans": spans})
    return out


def gen_examples(eval_only):
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


if args.smoke:
    print("[smoke] 토크나이저 offset 지원:", flush=True)
    e = tok("신청인 홍길동 (880101-1234568)", return_offsets_mapping=True)
    print(f"  offsets[:6]={e['offset_mapping'][:6]}", flush=True)
    print("[smoke] 모델 로딩(CPU bf16)...", flush=True)
    m = Gemma4TokenClassifier(args.base, len(LABELS))
    n = sum(p.numel() for p in m.parameters())
    print(f"  파라미터 {n/1e9:.2f}B (텍스트 타워+헤드)", flush=True)
    with torch.no_grad():
        out = m(input_ids=torch.tensor([e["input_ids"]]),
                attention_mask=torch.tensor([e["attention_mask"]]))
    print(f"  forward OK — logits {tuple(out.logits.shape)} (라벨 {len(LABELS)})", flush=True)
    sys.exit(0)

train_ex = kdpii_examples("train")
g = gen_examples(eval_only=False); train_ex += g
print(f"학습: KDPII {len(train_ex)-len(g)} + 생성행정 {len(g)} = {len(train_ex)}", flush=True)
print(f"[{args.base}] 라벨 {len(ENT)}종 · 토큰화...", flush=True)
train_ds = make_ds(train_ex)
val_ds = make_ds(kdpii_examples("valid"))
test_kd = make_ds(kdpii_examples("test"))
test_gen = make_ds(gen_examples(eval_only=True))
print(f"train {len(train_ds)} / valid {len(val_ds)} / KDPII test {len(test_kd)} / 생성 test {len(test_gen)}", flush=True)

model = Gemma4TokenClassifier(args.base, len(LABELS))


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
    per_device_train_batch_size=args.bs, per_device_eval_batch_size=16,
    gradient_accumulation_steps=args.accum, gradient_checkpointing=True,
    learning_rate=args.lr, warmup_ratio=0.1, weight_decay=0.01,
    bf16=True, optim="adamw_torch_fused",
    eval_strategy="epoch", save_strategy="epoch", save_total_limit=1,
    load_best_model_at_end=True, metric_for_best_model="f1",
    logging_steps=100, report_to=[], eval_accumulation_steps=8,
    label_names=["labels"])
trainer = Trainer(model=model, args=targ, train_dataset=train_ds, eval_dataset=val_ds,
                  data_collator=DataCollatorForTokenClassification(tok), compute_metrics=compute)
trainer.train()

res = {"base": args.base, "all_labels": True, "lr": args.lr, "epochs": args.epochs}
for name, ds in [("KDPII_test", test_kd), ("generated_540", test_gen)]:
    pr = trainer.predict(ds)
    P, L = decode(pr.predictions, pr.label_ids)
    print(f"\n==== [{args.base}] {name} ====", flush=True)
    print(f"overall F1={f1_score(L,P):.3f} P={precision_score(L,P):.3f} R={recall_score(L,P):.3f}", flush=True)
    print(classification_report(L, P, digits=3, zero_division=0), flush=True)
    res[name] = {"f1": f1_score(L, P), "precision": precision_score(L, P), "recall": recall_score(L, P)}

os.makedirs(args.out, exist_ok=True)
torch.save({"classifier": model.classifier.state_dict(), "labels": LABELS},
           args.out + "/head.pt")
model.backbone.save_pretrained(args.out + "/final_backbone")
tok.save_pretrained(args.out + "/final_backbone")
json.dump(res, open(args.out + "/result.json", "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {args.out} (backbone + head.pt + result.json)", flush=True)
