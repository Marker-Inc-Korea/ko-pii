#!/usr/bin/env python3
"""체크섬 프로브 — 룰(검증) vs 전체학습 ML(패턴매칭)의 질적 차이 시연.

유효/무효(체크섬 깨짐)/포맷 변형 ID에 대해 두 검출기의 판정을 비교한다.
ML이 체크섬을 검증하지 못함(무효 번호도 검출)과 포맷 일반화 차이를 보는 목적.
usage: checksum_probe.py [model_dir]
"""
import os, sys
os.environ.setdefault("HF_HOME", "/data1/mk04/.cache/huggingface")
sys.path.insert(0, "/data1/mk04/projects/ko-pii/src")
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from ko_pii.detect import detect_all

M = sys.argv[1] if len(sys.argv) > 1 else "/data1/mk04/pii_ner/out/klue_all_slurm/final"


def rrn(base12):
    w = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    d = [int(c) for c in base12]
    chk = (11 - sum(a * b for a, b in zip(d, w)) % 11) % 10
    return base12[:6] + "-" + base12[6:] + str(chk)


def luhn(base15):
    s = 0
    for i, c in enumerate(reversed(base15)):
        n = int(c)
        if i % 2 == 0:
            n *= 2
            n = n - 9 if n > 9 else n
        s += n
    return base15 + str((10 - s % 10) % 10)


v_rrn = rrn("850101123456")
i_rrn = v_rrn[:-1] + str((int(v_rrn[-1]) + 1) % 10)
vc = luhn("123456789012345")
v_card = f"{vc[:4]}-{vc[4:8]}-{vc[8:12]}-{vc[12:]}"
i_card = v_card[:-1] + str((int(v_card[-1]) + 1) % 10)

tests = [
    ("유효 RRN (표준)", f"민원인 김철수의 주민등록번호는 {v_rrn} 입니다."),
    ("무효 RRN (체크섬 깨짐)", f"민원인 김철수의 주민등록번호는 {i_rrn} 입니다."),
    ("유효 RRN (하이픈 없음)", f"주민등록번호 {v_rrn.replace('-', '')} 확인 바랍니다."),
    ("유효 카드 (표준)", f"결제 카드번호 {v_card} 로 처리되었습니다."),
    ("무효 카드 (Luhn 깨짐)", f"결제 카드번호 {i_card} 로 처리되었습니다."),
    ("유효 RRN (공백 변형)", f"주민번호 : {v_rrn[:6]} - {v_rrn[7:]} 조회 요청."),
]

tok = AutoTokenizer.from_pretrained(M)
model = AutoModelForTokenClassification.from_pretrained(M).eval()
ID2L = model.config.id2label


@torch.no_grad()
def ml(text):
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
    return [(l, text[s:e]) for l, s, e in out]


print(f"{'케이스':22s} | {'ko-pii 룰(체크섬 검증)':30s} | ML 전체학습(패턴)")
print("-" * 100)
for name, text in tests:
    rule = [(r.label, r.text) for r in detect_all(text) if r.label in ("RRN", "CARD")]
    mlr = [(l, v) for l, v in ml(text) if l in ("RRN", "CARD")]
    print(f"{name:22s} | {str(rule):30s} | {mlr}")
