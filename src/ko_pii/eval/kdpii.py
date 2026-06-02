"""KDPII (Korean Dialog PII) 벤치마크 어댑터.

KDPII 코퍼스 (KAIST/KETI 한국어 대화체 PII 데이터셋) 의 JSONL 포맷을 읽어
ko-pii detect_all 출력과 라벨별 P/R/F1 측정.

데이터 포맷 (per line):
    {
      "query": "<대화 텍스트>",
      "answer": [{"label": "PS_NAME", "form": "김민지"}, ...]
    }

KDPII 라벨 → ko-pii LABEL 매핑은 ``KDPII_LABEL_MAP`` 참조. 본 매핑은
2026-05-19 시점 KDPII 라벨 분포 직접 조사로 정정 (초기 매핑 오류 사례
docs/kdpii_session_report.md D-011 참조).

매칭 정책: **substring overlap** — 예측 텍스트가 gold form 의 부분 문자열
이거나 그 반대일 경우 TP. ``010-1234-5678`` 검출이 gold ``010 1234 5678``
과도 매칭되도록.

사용:
    from ko_pii.eval.kdpii import load_kdpii, evaluate_kdpii, format_kdpii_report

    docs = load_kdpii("kdpii.jsonl")
    report = evaluate_kdpii(docs)
    print(format_kdpii_report(report))
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ko_pii.core.types import DetectionResult
from ko_pii.detect import detect_all


# KDPII 라벨 → ko-pii LABEL 매핑.
# (PS_NAME / OGG_EDUCATION 같이 KDPII 가 사용하는 정식 라벨 기준)
#
# 매핑 안 된 KDPII 라벨 (ko-pii 스코프 밖):
#   PS_NICKNAME (별명)  — 가명 vs PII 모호, 별도 카테고리 미구현
#   OGG_CLUB / OGG_RELIGION — 소속 단체, 별도 카테고리 미구현
#   LC_PLACE — 일반 장소 (특정 행정구역 아닌 명사), ADDRESS 와 분리
#   OG_WORKPLACE / OG_DEPARTMENT — 회사·부서명, 별도 카테고리 미구현
#   CV_SEX / CV_MILITARY_CAMP / TM_BLOOD_TYPE / QT_GRADE — 미구현
#   LCP_COUNTRY — 국가명 (우리는 ADDRESS 의 country kind 로 처리)
KDPII_LABEL_MAP: dict[str, str] = {
    "PS_NAME": "PERSON",
    "QT_AGE": "AGE",
    "OGG_EDUCATION": "EDUCATION",
    "FD_MAJOR": "MAJOR",
    "CV_POSITION": "POSITION",
    "DT_BIRTH": "DT_BIRTH",
    "QT_PHONE": "PHONE",
    "QT_MOBILE": "PHONE",
    "TMI_EMAIL": "EMAIL",
    "TMI_SITE": "URL",  # 웹사이트 = URL
    "QT_RESIDENT_NUMBER": "RRN",
    "LC_ADDRESS": "ADDRESS",
    "LCP_COUNTRY": "ADDRESS",  # 국가 = ADDRESS (admin_alone country kind)
    "QT_CARD_NUMBER": "CARD",
    "QT_ACCOUNT_NUMBER": "ACCOUNT",
    "QT_PASSPORT_NUMBER": "PASSPORT",
    "QT_DRIVER_NUMBER": "DRIVER_LICENSE",
    "QT_IP": "IP",
    "QT_ALIEN_NUMBER": "FRN",
    "QT_PLATE_NUMBER": "VEHICLE",
    "QT_LENGTH": "HEIGHT",
    "QT_WEIGHT": "WEIGHT",
}


@dataclass
class KdpiiDocument:
    query: str
    gold: dict[str, set[str]] = field(default_factory=dict)  # label → {form}


@dataclass
class LabelMetrics:
    label: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class KdpiiReport:
    per_label: dict[str, LabelMetrics] = field(default_factory=dict)
    n_documents: int = 0

    @property
    def micro_tp(self) -> int:
        return sum(m.tp for m in self.per_label.values())

    @property
    def micro_fp(self) -> int:
        return sum(m.fp for m in self.per_label.values())

    @property
    def micro_fn(self) -> int:
        return sum(m.fn for m in self.per_label.values())

    @property
    def micro_precision(self) -> float:
        t, f = self.micro_tp, self.micro_fp
        return t / (t + f) if t + f else 0.0

    @property
    def micro_recall(self) -> float:
        t, f = self.micro_tp, self.micro_fn
        return t / (t + f) if t + f else 0.0

    @property
    def micro_f1(self) -> float:
        p, r = self.micro_precision, self.micro_recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _from_jsonl_record(d: dict) -> KdpiiDocument:
    """Original JSONL schema (cloud session input): {query, answer:[{label,form}]}."""
    doc = KdpiiDocument(query=d["query"])
    for a in d.get("answer", []):
        mapped = KDPII_LABEL_MAP.get(a["label"])
        if mapped is None:
            continue
        doc.gold.setdefault(mapped, set()).add(a["form"])
    return doc


def _from_zenodo_record(d: dict) -> KdpiiDocument:
    """Zenodo schema (record 10968609): {sentence, PII_set:[{label,form,begin,end}], ...}."""
    doc = KdpiiDocument(query=d.get("sentence", ""))
    for a in d.get("PII_set", []):
        label = a.get("label")
        form = a.get("form")
        if not label or not form:
            continue
        mapped = KDPII_LABEL_MAP.get(label)
        if mapped is None:
            continue
        doc.gold.setdefault(mapped, set()).add(form)
    return doc


def load_kdpii(path: str | Path) -> list[KdpiiDocument]:
    """KDPII 로더 — 입력 형식 자동 감지.

    - Zenodo JSON (record 10968609): top-level array, 각 record는 ``sentence``/
      ``PII_set`` 필드. ``train.json`` / ``valid.json`` / ``test.json`` 모두 이 형식.
    - 원래 JSONL: 라인당 ``{query, answer}`` (cloud session 처리본).

    매핑 안 된 KDPII 라벨은 무시 (``KDPII_LABEL_MAP`` 참조).
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    docs: list[KdpiiDocument] = []
    if stripped.startswith("["):
        # Zenodo JSON array
        for d in json.loads(text):
            docs.append(_from_zenodo_record(d))
    else:
        # JSONL
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if "sentence" in d and "PII_set" in d:
                docs.append(_from_zenodo_record(d))
            else:
                docs.append(_from_jsonl_record(d))
    return docs


def _matched_overlap(pred: set[str], gold: set[str]) -> tuple[set[str], set[str]]:
    """``(matched_pred, matched_gold)`` substring overlap 매칭.

    예측 텍스트가 gold form 의 부분이거나 반대이면 TP. 1:N / N:1 모두 허용
    (per-label set 평가; 위치 무시).
    """
    mp: set[str] = set()
    mg: set[str] = set()
    for pi in pred:
        for gi in gold:
            # 정확 일치, 또는 한쪽이 다른 쪽을 포함하되 *짧은 쪽이 2자 이상* 일 때만 TP.
            # (1자 성씨 예측이 풀네임 gold 의 부분문자열로 TP 처리되어 recall 을
            #  부풀리던 문제 방지.)
            if pi == gi or ((pi in gi or gi in pi) and min(len(pi), len(gi)) >= 2):
                mp.add(pi)
                mg.add(gi)
    return mp, mg


def evaluate_kdpii(
    docs: Iterable[KdpiiDocument],
    detector: Callable[[str], Iterable[DetectionResult]] = detect_all,
    *,
    person_min_length: int = 1,
) -> KdpiiReport:
    """KDPII 평가.

    ``person_min_length``: PERSON gold form 의 최소 길이.
    - 1 (기본): 모든 PERSON 평가
    - 3: 풀네임 (3자+) 만 평가 — 한국어 PII 정의 (제2조: 단독 별명·1-2자 이름은
      그 자체로 PII 아님) 에 부합. 외자 이름·단성 성씨 제외.

    예측 (prediction) 도 동일한 길이 필터 적용.
    """
    report = KdpiiReport()
    for doc in docs:
        report.n_documents += 1
        pred_by_label: dict[str, set[str]] = defaultdict(set)
        for r in detector(doc.query):
            # PERSON 예측도 길이 필터 적용 (gold 기준과 일치)
            if r.label == "PERSON" and len(r.text) < person_min_length:
                continue
            pred_by_label[r.label].add(r.text)
        for lab in set(doc.gold) | set(pred_by_label):
            g = doc.gold.get(lab, set())
            # PERSON gold 도 길이 필터
            if lab == "PERSON" and person_min_length > 1:
                g = {gi for gi in g if len(gi) >= person_min_length}
            p = pred_by_label.get(lab, set())
            mp, mg = _matched_overlap(p, g)
            m = report.per_label.setdefault(lab, LabelMetrics(label=lab))
            m.tp += len(mp)
            m.fp += len(p - mp)
            m.fn += len(g - mg)
    return report


def format_kdpii_report(report: KdpiiReport) -> str:
    lines: list[str] = []
    lines.append(f"문서 수: {report.n_documents}")
    lines.append(f"라벨 매핑: {len(KDPII_LABEL_MAP)} KDPII → "
                 f"{len(set(KDPII_LABEL_MAP.values()))} ko-pii LABEL")
    lines.append("")
    lines.append(f"{'라벨':<15}{'정탐':>6}{'오탐':>6}{'미탐':>6}{'정확도':>8}{'재현율':>8}{'F1':>8}")
    lines.append("-" * 57)
    for lab in sorted(report.per_label):
        m = report.per_label[lab]
        lines.append(
            f"{lab:<15}{m.tp:>6}{m.fp:>6}{m.fn:>6}"
            f"{m.precision:>8.3f}{m.recall:>8.3f}{m.f1:>8.3f}"
        )
    lines.append("-" * 57)
    lines.append(
        f"{'(전체)':<15}{report.micro_tp:>6}{report.micro_fp:>6}{report.micro_fn:>6}"
        f"{report.micro_precision:>8.3f}{report.micro_recall:>8.3f}"
        f"{report.micro_f1:>8.3f}"
    )
    lines.append("")
    lines.append("정탐 = 정확히 잡은 것 (gold 도 있음)")
    lines.append("오탐 = 잘못 잡은 것 (gold 없는데 잡음)")
    lines.append("미탐 = 놓친 것 (gold 있는데 못 잡음)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ko-pii-kdpii",
        description="KDPII 코퍼스에서 ko-pii 검출 정확도 평가",
    )
    p.add_argument("path", help="KDPII JSONL 파일")
    p.add_argument("--person-min-length", type=int, default=3,
                   help="PERSON 최소 길이 (기본 3 — 풀네임만 평가, "
                        "한국 개인정보보호법 제2조: 단독 1-2자 별명은 "
                        "그 자체로 PII 아님). 1 로 두면 별명 포함.")
    args = p.parse_args(argv)
    docs = load_kdpii(args.path)
    report = evaluate_kdpii(docs, person_min_length=args.person_min_length)
    print(format_kdpii_report(report))
    if args.person_min_length >= 3:
        print(f"\n※ PERSON 평가는 풀네임 ({args.person_min_length}자+) 만 — "
              "단독 1-2자 별명 제외 (제2조: 그 자체로 식별 불가)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
