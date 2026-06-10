#!/usr/bin/env python3
"""탐지·마스킹 시연 — 룰(ko-pii) vs ML(전체학습 NER) 실제 출력 비교.

모델은 '어디부터 어디까지가 무슨 PII 인지'(span+label)만 출력한다 — 마스킹은
그 span 에 대한 후처리이며, 룰 검출이든 ML 검출이든 같은 후처리를 꽂을 수 있음을 시연.
usage: mask_demo.py <model_dir>   (인자 생략 시 환경변수 KO_PII_NER_MODEL 사용)
"""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]  # 레포 루트 (experiments/ner/code/ 기준)
sys.path.insert(0, str(ROOT / "src"))
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from ko_pii import Anonymizer
from ko_pii.detect import detect_all

M = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("KO_PII_NER_MODEL", "")
if not M:
    sys.exit("usage: mask_demo.py <model_dir>   (또는 환경변수 KO_PII_NER_MODEL 설정)")
TEXT = "신청인 홍길동 (880101-1234568) 연락처 010-1234-5678\n주소: 서울특별시 강남구 테헤란로 152"

print("원문:")
print("  " + TEXT.replace("\n", "\n  "))

# ── 1. ko-pii 룰 파이프라인 ─────────────────────────────
print("\n[1] ko-pii 룰 — 검출 span:")
for r in detect_all(TEXT):
    print(f"  {r.label:10s} {r.start:>3d}-{r.end:<3d} '{r.text}'  (risk={r.risk_level.name}, conf={r.confidence})")

for strat in ("tokenize", "partial", "redact"):
    try:
        res = Anonymizer(strategy=strat).process(TEXT)
        out = getattr(res, "anonymized_text", None) or getattr(res, "text", str(res))
        print(f"\n[1] ko-pii 룰 + {strat}:")
        print("  " + out.replace("\n", "\n  "))
    except Exception as e:
        print(f"\n[1] {strat}: 미지원 ({e})")

# ── 2. ML(전체학습 NER) 원시 출력 ───────────────────────
tok = AutoTokenizer.from_pretrained(M)
model = AutoModelForTokenClassification.from_pretrained(M).eval()  # CPU
ID2L = model.config.id2label


@torch.no_grad()
def ml_spans(text):
    enc = tok(text, return_offsets_mapping=True, return_tensors="pt",
              truncation=True, max_length=256)
    offs = enc.pop("offset_mapping")[0].tolist()
    pred = model(**enc).logits[0].argmax(-1).tolist()
    out, cur = [], None
    for (s, e), p in zip(offs, pred):
        if s == e:
            continue
        t = ID2L[p]
        if t == "O":
            cur = None
            continue
        pos, lab = t.split("-", 1)
        if pos == "B" or not cur or cur[0] != lab:
            out.append([lab, s, e])
            cur = (lab,)
        else:
            out[-1][2] = e
    return [(l, s, e, text[s:e]) for l, s, e in out]


spans = ml_spans(TEXT)
print("\n[2] ML(전체학습 NER) — 모델의 실제 출력 = span + label (이게 전부):")
for lab, s, e, v in spans:
    print(f"  {lab:10s} {s:>3d}-{e:<3d} '{v}'")

# ── 3. ML 검출 + 마스킹 후처리 (동일 span-치환 로직) ─────
KO = {"PERSON": "성명", "RRN": "주민등록번호", "PHONE": "전화번호", "ADDRESS": "주소",
      "EMAIL": "이메일", "CARD": "카드번호", "ACCOUNT": "계좌번호"}


def apply(spans, text, mode):
    counts, out = {}, text
    for lab, s, e, v in sorted(spans, key=lambda x: -x[1]):
        if mode == "tokenize":
            counts[lab] = counts.get(lab, 0) + 1
            rep = f"<{lab}_{counts[lab]}>"
        else:  # redact
            rep = f"[{KO.get(lab, lab)}]"
    # tokenize 번호는 등장 순서로 — 역순 치환했으니 재계산
    if mode == "tokenize":
        counts, parts, pos = {}, [], 0
        out_l = []
        for lab, s, e, v in sorted(spans, key=lambda x: x[1]):
            counts[lab] = counts.get(lab, 0) + 1
            out_l.append((s, e, f"<{lab}_{counts[lab]}>"))
        for s, e, rep in reversed(out_l):
            out = out[:s] + rep + out[e:]
        return out
    for lab, s, e, v in sorted(spans, key=lambda x: -x[1]):
        out = out[:s] + f"[{KO.get(lab, lab)}]" + out[e:]
    return out


for mode in ("tokenize", "redact"):
    print(f"\n[3] ML 검출 + {mode} 후처리:")
    print("  " + apply(spans, TEXT, mode).replace("\n", "\n  "))

print("""
※ partial(일부 가림: 홍** 등)은 카테고리별 포맷 규칙(성명 첫 자만, RRN 앞 7자리만 등)이
  필요한 후처리로, ko-pii 내장 포매터에 ML span 을 그대로 꽂으면 동일하게 동작한다.
  즉 '모델은 마스킹이 안 된다'가 아니라 — 모델은 탐지(span)까지, 마스킹은 공용 후처리.""")
