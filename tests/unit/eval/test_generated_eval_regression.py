"""회귀 게이트 — 커밋된 합성 평가셋(data/generated_eval.jsonl)으로 ko-pii F1 하한 검증.

ko-pii 는 결정적이므로 이 평가셋에 대한 점수는 안정적이다. 룰/사전 변경이 검출
성능을 떨어뜨리면 이 테스트가 CI 에서 실패해 회귀를 막는다. (CI 는 `pytest -q` 실행)

기준값(측정): 전체 F1 ≈ 0.790. 사소한 변동 여유를 두고 하한을 0.78 로 둔다.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from ko_pii.detect import detect_all
from ko_pii.eval.kdpii import match_forms_overlap

DATA = Path(__file__).resolve().parents[3] / "data" / "generated_eval.jsonl"
PML = 3  # person_min_length


def _load():
    if not DATA.exists():
        pytest.fail(f"평가셋 누락: {DATA} (레포에 커밋되어 있어야 함)")
    return [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]


def _score():
    docs = _load()
    per = defaultdict(lambda: [0, 0, 0])  # label -> [tp, fp, fn]
    tp = fp = fn = 0
    for d in docs:
        gold = defaultdict(set)
        for p in d["pii"]:
            if p["type"] == "PERSON" and len(p["text"]) < PML:
                continue
            gold[p["type"]].add(p["text"])
        pred = defaultdict(set)
        for r in detect_all(d["text"]):
            if r.label == "PERSON" and len(r.text) < PML:
                continue
            pred[r.label].add(r.text)
        for lab in set(gold) | set(pred):
            mp, mg = match_forms_overlap(pred.get(lab, set()), gold.get(lab, set()))
            tp += len(mp); fp += len(pred.get(lab, set()) - mp); fn += len(gold.get(lab, set()) - mg)
            per[lab][0] += len(mp); per[lab][1] += len(pred.get(lab, set()) - mp); per[lab][2] += len(gold.get(lab, set()) - mg)
    return tp, fp, fn, per


def _f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def test_overall_f1_floor():
    tp, fp, fn, _ = _score()
    f1 = _f1(tp, fp, fn)
    assert f1 >= 0.78, f"ko-pii 전체 F1 {f1:.3f} < 0.78 (회귀 의심)"


@pytest.mark.parametrize("label,floor", [
    ("RRN", 0.90), ("PHONE", 0.95), ("EMAIL", 0.95), ("CARD", 0.95),
    ("ADDRESS", 0.90), ("ACCOUNT", 0.90),
    # 형식 확장으로 0.0 → 정상화된 라벨 (락인)
    ("MEDICAL_INSURANCE", 0.70), ("PRESCRIPTION_ID", 0.55),
])
def test_per_label_floor(label, floor):
    _, _, _, per = _score()
    tp, fp, fn = per[label]
    f1 = _f1(tp, fp, fn)
    assert f1 >= floor, f"{label} F1 {f1:.3f} < {floor} (gold {tp + fn})"
