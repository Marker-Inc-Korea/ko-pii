"""Model comparison eval — ko-pii vs HF privacy-filter models.

Strategy (per user 2026-05-21):
  Use HF model output as **pseudo-ground-truth** for shared label categories.
  ko-pii unique categories (RRN/사업자/법인/운전면허 — Korean-specific) are
  reported separately with no GT comparison ("ko-pii unique coverage").

This is NOT real ground truth — it measures agreement with the HF model.
For Korean text, especially when the HF model wasn't card-tagged for
Korean, take results with a grain of salt. KDPII provides actual GT and
is evaluated separately via `ko_pii.eval.kdpii`.

Default GT model: `openai/privacy-filter` (33 labels, ~660M params, fp16
~1.8 GB VRAM). OpenMed/privacy-filter-multilingual is officially
Korean-supporting (217 labels). Both share the `openai_privacy_filter`
custom architecture → `trust_remote_code=True` required.

CLI:
    python -m ko_pii.eval.model_comparison data/corpus/aihub_combined.txt \\
        --model openai/privacy-filter --max-docs 500
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Only import torch/transformers when actually running (keeps ko-pii core ML-free)


# openai/privacy-filter label → ko-pii LABEL mapping.
# Confirmed by loading the model and reading id2label (8 categories with BIOES
# tagging = 33 labels total). The model uses `private_*` prefix.
OPENAI_TO_KPII: dict[str, str] = {
    "private_person": "PERSON",
    "private_email": "EMAIL",
    "private_phone": "PHONE",
    "private_address": "ADDRESS",
    "private_date": "DT_BIRTH",     # closest ko-pii analogue
    "private_url": "URL",
    "account_number": "ACCOUNT",    # also collides with RRN in Korean documents
                                    # (the model has no separate RRN label)
    # `secret` is generic (passwords/API keys); no clean ko-pii analogue — drop
}


# OpenMed/privacy-filter-multilingual label mapping (54 categories, 217 BIOES tags).
# 한국어 공식 지원 ('ko' tag).  Same `openai_privacy_filter` architecture as
# openai/privacy-filter — trust_remote_code=True 필요.
#
# 흥미로운 한국 핵심 PII 커버:
#   SSN          → RRN candidate (US/EU SSN format 위주이지만 한국 RRN 시도)
#   FIRSTNAME    → PERSON (ko-pii 풀네임으로 결합 필요)
#   LASTNAME     → PERSON
#   MIDDLENAME   → PERSON
#   VRM/VIN      → VEHICLE
#   JOBTITLE     → POSITION
#
OPENMED_TO_KPII: dict[str, str] = {
    # 이름 (composite — ko-pii PERSON 으로 통합)
    "FIRSTNAME": "PERSON",
    "LASTNAME": "PERSON",
    "MIDDLENAME": "PERSON",
    # 연락 정보
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "URL": "URL",
    "USERAGENT": None,  # 무관
    "USERNAME": None,
    "PASSWORD": None,
    # 식별번호
    "SSN": "RRN",  # 한국 RRN 형식 시도 (가능성)
    "CREDITCARD": "CARD",
    "BANKACCOUNT": "ACCOUNT",
    "ACCOUNTNAME": None,  # 은행 이름은 PII 아님
    "BIC": "ACCOUNT",
    "IBAN": "ACCOUNT",
    # 주소
    "CITY": "ADDRESS",
    "STATE": "ADDRESS",
    "COUNTY": "ADDRESS",
    "STREET": "ADDRESS",
    "ZIPCODE": "POSTAL_CODE",
    "BUILDINGNUMBER": "ADDRESS",
    "SECONDARYADDRESS": "ADDRESS",
    "ORDINALDIRECTION": None,
    "GPSCOORDINATES": "ADDRESS",
    # 차량
    "VRM": "VEHICLE",  # Vehicle Registration Mark
    "VIN": "VEHICLE",  # Vehicle Identification Number
    # 직책 / 직장
    "JOBTITLE": "POSITION",
    "OCCUPATION": "POSITION",
    "JOBDEPARTMENT": None,  # 부서명 = 일반 조직 정보
    "ORGANIZATION": None,
    # 날짜 / 시간
    "DATEOFBIRTH": "DT_BIRTH",
    "DATE": None,  # generic — DT_BIRTH 아님
    "TIME": None,
    # 인적 속성
    "AGE": "AGE",
    "HEIGHT": "HEIGHT",
    "GENDER": None,  # ko-pii 미구현
    "SEX": None,
    "EYECOLOR": None,
    # 네트워크
    "IPADDRESS": "IP",
    "MACADDRESS": None,
    "IMEI": None,
    # 금융 (ko-pii 스코프 밖)
    "AMOUNT": None,
    "CURRENCY": None,
    "CURRENCYCODE": None,
    "CURRENCYNAME": None,
    "CURRENCYSYMBOL": None,
    "BITCOINADDRESS": None,
    "ETHEREUMADDRESS": None,
    "LITECOINADDRESS": None,
    "CVV": "CARD",  # 카드 CVV
    "PIN": None,
    "MASKEDNUMBER": None,
    # 호칭
    "PREFIX": None,  # "Mr."/"Ms." 등
}


# ko-pii LABELs we treat as Korean-only (no HF analogue, reported separately)
KPII_KOREAN_ONLY = {
    "RRN", "FRN", "BUSINESS_REG", "CORP_REG", "DRIVER_LICENSE",
    "VEHICLE", "PASSPORT", "MEDICAL_INSURANCE",
}


@dataclass
class Span:
    start: int
    end: int
    label: str
    text: str


@dataclass
class LabelMetrics:
    label: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class ComparisonReport:
    per_label: dict[str, LabelMetrics] = field(default_factory=dict)
    kpii_only_counts: dict[str, int] = field(default_factory=dict)
    n_documents: int = 0
    gt_model: str = ""
    corpus_label: str = ""

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
    def micro_f1(self) -> float:
        t, f, n = self.micro_tp, self.micro_fp, self.micro_fn
        p = t / (t + f) if (t + f) else 0.0
        r = t / (t + n) if (t + n) else 0.0
        return 2 * p * r / (p + r) if (p + r) else 0.0


class HFPrivacyDetector:
    """Wrapper over a HuggingFace token-classification privacy model.

    Two backends:
      - "torch" (default if available): transformers + torch
      - "onnx":   onnxruntime + tokenizers (no transformers/torch needed)

    Use the ONNX backend when torch/transformers version pinning is painful
    (e.g., Python 3.13 had a window where torch 2.6 was the latest cu126 wheel
    but transformers 5.x needed torch 2.7+ AuxRequest). ONNX is also smaller
    on disk: openai/privacy-filter ships an `onnx/model_q4f16.onnx` (~770 MB)
    that runs on consumer GPU comfortably.
    """

    def __init__(
        self,
        model_id: str,
        *,
        device: str | None = None,
        max_seq_len: int = 1024,
        batch_size: int = 8,
        backend: str = "auto",
        onnx_file: str = "onnx/model_q4f16.onnx",
        cache_dir: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.max_seq_len = max_seq_len
        self.batch_size = batch_size

        if backend == "auto":
            backend = self._auto_backend()
        self.backend = backend
        if backend == "torch":
            self._init_torch(device)
        elif backend == "onnx":
            self._init_onnx(device, onnx_file, cache_dir)
        else:
            raise ValueError(f"unknown backend: {backend}")

    @staticmethod
    def _auto_backend() -> str:
        # Prefer torch if transformers can load this model.
        # Fall back to onnx otherwise.
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForTokenClassification  # noqa: F401
            # Try a cheap sanity check — actual load happens later in _init_torch.
            return "torch"
        except ImportError:
            return "onnx"

    # ---------- torch backend ----------

    def _init_torch(self, device: str | None) -> None:
        import torch
        from transformers import AutoTokenizer, AutoModelForTokenClassification

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, trust_remote_code=True
        )
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.model = (
            AutoModelForTokenClassification.from_pretrained(
                self.model_id, trust_remote_code=True, torch_dtype=dtype
            )
            .to(device)
            .eval()
        )
        self.id2label = self.model.config.id2label
        self._torch = torch

    # ---------- onnx backend ----------

    def _init_onnx(self, device: str | None, onnx_file: str, cache_dir: str | None) -> None:
        import json
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from tokenizers import Tokenizer

        if device is None:
            device = "cuda" if "CUDAExecutionProvider" in ort.get_available_providers() else "cpu"
        self.device = device

        # Pull required files from HF hub
        path = snapshot_download(
            self.model_id,
            allow_patterns=[
                "config.json", "tokenizer.json", "tokenizer_config.json",
                onnx_file, onnx_file + "_data",
            ],
            cache_dir=cache_dir,
        )
        from pathlib import Path
        root = Path(path)
        with open(root / "config.json", encoding="utf-8") as fh:
            cfg = json.load(fh)
        self.id2label = {int(k): v for k, v in cfg.get("id2label", {}).items()}
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))

        # Provider selection. Some onnxruntime-gpu installs report
        # CUDAExecutionProvider as available but session creation fails
        # (missing cuDNN 9 / CUDA 12 dlls on Windows) — silently falls back.
        # DML EP is also available on Windows but has known correctness issues
        # with q4f16 quantized models (returns all-O predictions). So we only
        # try DML if user opts in explicitly via device='dml'.
        available = set(ort.get_available_providers())
        candidates = []
        if device == "cuda" and "CUDAExecutionProvider" in available:
            candidates.append("CUDAExecutionProvider")
        if device == "dml" and "DmlExecutionProvider" in available:
            candidates.append("DmlExecutionProvider")
        candidates.append("CPUExecutionProvider")
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(root / onnx_file), sess_options=so, providers=candidates
        )
        # Verify which provider actually got used
        used = self.session.get_providers()
        self.device = "cuda" if used and used[0] == "CUDAExecutionProvider" else (
            "dml" if used and used[0] == "DmlExecutionProvider" else "cpu"
        )
        self._input_name = self.session.get_inputs()[0].name
        self._input_names = [i.name for i in self.session.get_inputs()]

    def detect(self, text: str) -> list[Span]:
        """Return entity spans found in *text*. Chunks long inputs."""
        return list(self._detect_chunks(text))

    def _detect_chunks(self, text: str) -> Iterable[Span]:
        if self.backend == "torch":
            yield from self._detect_chunks_torch(text)
        else:
            yield from self._detect_chunks_onnx(text)

    # ----- torch chunked detect -----

    def _detect_chunks_torch(self, text: str) -> Iterable[Span]:
        torch = self._torch
        encoded = self.tokenizer(
            text,
            return_offsets_mapping=True,
            return_tensors=None,
            add_special_tokens=False,
            truncation=False,
        )
        ids: list[int] = encoded["input_ids"]
        offsets: list[tuple[int, int]] = encoded["offset_mapping"]
        if not ids:
            return

        i = 0
        while i < len(ids):
            j = min(i + self.max_seq_len, len(ids))
            chunk_ids = ids[i:j]
            chunk_offsets = offsets[i:j]
            with torch.no_grad():
                inputs = torch.tensor([chunk_ids], device=self.device)
                logits = self.model(inputs).logits[0]
                pred_ids = logits.argmax(dim=-1).tolist()
            yield from self._decode_bioes(pred_ids, chunk_offsets, text)
            i = j

    # ----- onnx chunked detect -----

    def _detect_chunks_onnx(self, text: str) -> Iterable[Span]:
        import numpy as np

        enc = self.tokenizer.encode(text, add_special_tokens=False)
        ids = enc.ids
        offsets = enc.offsets
        if not ids:
            return

        i = 0
        while i < len(ids):
            j = min(i + self.max_seq_len, len(ids))
            chunk_ids = ids[i:j]
            chunk_offsets = offsets[i:j]
            input_ids = np.array([chunk_ids], dtype=np.int64)
            feed: dict = {self._input_names[0]: input_ids}
            if "attention_mask" in self._input_names:
                feed["attention_mask"] = np.ones_like(input_ids)
            if "position_ids" in self._input_names:
                feed["position_ids"] = np.arange(len(chunk_ids), dtype=np.int64).reshape(1, -1)
            outs = self.session.run(None, feed)
            logits = outs[0][0]  # (seq, n_labels)
            pred_ids = logits.argmax(axis=-1).tolist()
            yield from self._decode_bioes(pred_ids, chunk_offsets, text)
            i = j

    def _decode_bioes(
        self, pred_ids: list[int], offsets: list[tuple[int, int]], text: str
    ) -> Iterable[Span]:
        current_label: str | None = None
        current_start: int | None = None
        last_end: int | None = None

        def flush() -> Span | None:
            nonlocal current_label, current_start, last_end
            if current_label is not None and current_start is not None and last_end is not None:
                s = Span(
                    start=current_start, end=last_end,
                    label=current_label, text=text[current_start:last_end],
                )
                current_label = None
                current_start = None
                last_end = None
                return s
            return None

        for pid, (start, end) in zip(pred_ids, offsets):
            tag = self.id2label.get(pid, "O")
            if tag == "O" or start == end:
                s = flush()
                if s is not None:
                    yield s
                continue
            bio, _, label = tag.partition("-")
            if not label:
                # malformed tag, treat as O
                s = flush()
                if s is not None:
                    yield s
                continue
            if bio in ("B", "S"):
                s = flush()
                if s is not None:
                    yield s
                current_label = label
                current_start = start
                last_end = end
                if bio == "S":
                    s = flush()
                    if s is not None:
                        yield s
            elif bio in ("I", "E"):
                if current_label == label:
                    last_end = end
                else:
                    s = flush()
                    if s is not None:
                        yield s
                    current_label = label
                    current_start = start
                    last_end = end
                if bio == "E":
                    s = flush()
                    if s is not None:
                        yield s
            else:
                s = flush()
                if s is not None:
                    yield s
        s = flush()
        if s is not None:
            yield s


def _kpii_spans(text: str) -> list[Span]:
    from ko_pii.detect import detect_all
    out: list[Span] = []
    for r in detect_all(text):
        out.append(Span(start=r.start, end=r.end, label=r.label, text=r.text))
    return out


def _spans_overlap(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end


def _compare_text(
    text: str,
    gt_spans: list[Span],
    pred_spans: list[Span],
    label_map: dict[str, str],
    report: ComparisonReport,
) -> None:
    # Translate GT labels to ko-pii naming for direct comparison
    gt_translated = []
    for s in gt_spans:
        mapped = label_map.get(s.label)
        if mapped is None:
            continue
        gt_translated.append(Span(s.start, s.end, mapped, s.text))

    by_gt_label: dict[str, list[Span]] = defaultdict(list)
    for s in gt_translated:
        by_gt_label[s.label].append(s)
    by_pred_label: dict[str, list[Span]] = defaultdict(list)
    for s in pred_spans:
        if s.label in KPII_KOREAN_ONLY:
            # Korean-only categories — record but exclude from F1
            report.kpii_only_counts[s.label] = report.kpii_only_counts.get(s.label, 0) + 1
            continue
        if s.label in label_map.values():
            by_pred_label[s.label].append(s)

    all_labels = set(by_gt_label) | set(by_pred_label)
    for lab in all_labels:
        gt = by_gt_label.get(lab, [])
        pred = by_pred_label.get(lab, [])
        matched_gt = [False] * len(gt)
        matched_pred = [False] * len(pred)
        for i, p in enumerate(pred):
            for j, g in enumerate(gt):
                if matched_gt[j]:
                    continue
                if _spans_overlap(p, g):
                    matched_pred[i] = True
                    matched_gt[j] = True
                    break
        m = report.per_label.setdefault(lab, LabelMetrics(label=lab))
        m.tp += sum(matched_pred)
        m.fp += sum(1 for x in matched_pred if not x)
        m.fn += sum(1 for x in matched_gt if not x)


def run_comparison(
    documents: Iterable[str],
    *,
    gt_model_id: str = "openai/privacy-filter",
    label_map: dict[str, str] | None = None,
    corpus_label: str = "",
) -> ComparisonReport:
    if label_map is None:
        label_map = OPENAI_TO_KPII

    detector = HFPrivacyDetector(gt_model_id)
    report = ComparisonReport(gt_model=gt_model_id, corpus_label=corpus_label)

    for doc in documents:
        if not doc.strip():
            continue
        report.n_documents += 1
        gt_spans = detector.detect(doc)
        pred_spans = _kpii_spans(doc)
        _compare_text(doc, gt_spans, pred_spans, label_map, report)
    return report


def format_report(report: ComparisonReport) -> str:
    lines: list[str] = []
    lines.append(f"코퍼스: {report.corpus_label}")
    lines.append(f"GT 모델: {report.gt_model} (pseudo-GT, not real ground truth)")
    lines.append(f"문서 수: {report.n_documents}")
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
        f"{'':>8}{'':>8}{report.micro_f1:>8.3f}"
    )
    lines.append("")
    if report.kpii_only_counts:
        lines.append("=== ko-pii unique coverage (no HF analogue) ===")
        for lab in sorted(report.kpii_only_counts):
            lines.append(f"  {lab}: {report.kpii_only_counts[lab]}")
    lines.append("")
    lines.append("주의: 정탐/오탐/미탐은 'GT 모델과의 일치' 기준이지 실제 정확도가 아님.")
    lines.append("Korean-specific 카테고리는 위 'ko-pii unique coverage' 참고.")
    return "\n".join(lines)


def _read_documents(path: Path, doc_sep: str = "\n\n") -> list[str]:
    text = path.read_text(encoding="utf-8")
    docs = [d.strip() for d in text.split(doc_sep)]
    return [d for d in docs if d and not d.startswith("===")]


def run_kdpii_three_way(
    kdpii_path: str | Path,
    *,
    gt_model_id: str = "openai/privacy-filter",
    backend: str = "auto",
    max_docs: int | None = None,
    person_min_length: int = 3,
    cache_dir: str | None = "./models",
) -> dict[str, ComparisonReport]:
    """Three-way evaluation on KDPII (which HAS real gold labels):
        - ko-pii vs KDPII gold
        - HF model vs KDPII gold
        - (ko-pii vs HF as pseudo-GT is in run_comparison())

    Returns two reports indexed by 'ko-pii' and 'hf'.
    """
    from ko_pii.eval.kdpii import KDPII_LABEL_MAP, load_kdpii
    from ko_pii.detect import detect_all

    docs = load_kdpii(kdpii_path)
    if max_docs:
        docs = docs[:max_docs]

    detector = HFPrivacyDetector(gt_model_id, backend=backend, cache_dir=cache_dir)

    kpii_rep = ComparisonReport(
        gt_model="KDPII gold (real human labels)",
        corpus_label=f"KDPII ({len(docs)} docs)",
    )
    hf_rep = ComparisonReport(
        gt_model="KDPII gold (real human labels)",
        corpus_label=f"KDPII ({len(docs)} docs)",
    )

    for doc in docs:
        text = doc.query
        if not text.strip():
            continue
        kpii_rep.n_documents += 1
        hf_rep.n_documents += 1

        # ko-pii predictions
        kpii_pred: dict[str, set[str]] = defaultdict(set)
        for r in detect_all(text):
            if r.label == "PERSON" and len(r.text) < person_min_length:
                continue
            kpii_pred[r.label].add(r.text)

        # HF predictions, mapped to ko-pii labels
        hf_pred: dict[str, set[str]] = defaultdict(set)
        for s in detector.detect(text):
            mapped = OPENAI_TO_KPII.get(s.label)
            if mapped is None:
                continue
            if mapped == "PERSON" and len(s.text.strip()) < person_min_length:
                continue
            hf_pred[mapped].add(s.text.strip())

        # KDPII gold (already mapped to ko-pii LABEL by load_kdpii)
        gold = dict(doc.gold)
        if person_min_length > 1 and "PERSON" in gold:
            gold["PERSON"] = {g for g in gold["PERSON"] if len(g) >= person_min_length}

        # Score each detector against gold
        for system_pred, report in [(kpii_pred, kpii_rep), (hf_pred, hf_rep)]:
            for lab in set(gold) | set(system_pred):
                g = gold.get(lab, set())
                p = system_pred.get(lab, set())
                matched_p: set[str] = set()
                matched_g: set[str] = set()
                for pi in p:
                    for gi in g:
                        if pi in gi or gi in pi:
                            matched_p.add(pi)
                            matched_g.add(gi)
                m = report.per_label.setdefault(lab, LabelMetrics(label=lab))
                m.tp += len(matched_p)
                m.fp += len(p - matched_p)
                m.fn += len(g - matched_g)

    return {"ko-pii": kpii_rep, "hf": hf_rep}


def format_kdpii_threeway(reports: dict[str, ComparisonReport]) -> str:
    kpii = reports["ko-pii"]
    hf = reports["hf"]
    lines: list[str] = []
    lines.append(f"KDPII 평가 ({kpii.n_documents} 문서) — gold = 실제 인간 라벨")
    lines.append(f"GT model used as third detector: {hf.gt_model.replace('KDPII gold', '')} (openai/privacy-filter)")
    lines.append("")
    lines.append(f"{'라벨':<15}  {'ko-pii(TP/FP/FN/F1)':<28}  {'HF(TP/FP/FN/F1)':<28}")
    lines.append("-" * 75)
    all_labels = sorted(set(kpii.per_label) | set(hf.per_label))
    for lab in all_labels:
        kp = kpii.per_label.get(lab, LabelMetrics(label=lab))
        hp = hf.per_label.get(lab, LabelMetrics(label=lab))
        lines.append(
            f"{lab:<15}  "
            f"{kp.tp:>4}/{kp.fp:>4}/{kp.fn:>4} F1={kp.f1:>5.3f}  "
            f"{hp.tp:>4}/{hp.fp:>4}/{hp.fn:>4} F1={hp.f1:>5.3f}"
        )
    lines.append("-" * 75)
    lines.append(
        f"{'(micro)':<15}  "
        f"{kpii.micro_tp:>4}/{kpii.micro_fp:>4}/{kpii.micro_fn:>4} F1={kpii.micro_f1:>5.3f}  "
        f"{hf.micro_tp:>4}/{hf.micro_fp:>4}/{hf.micro_fn:>4} F1={hf.micro_f1:>5.3f}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ko-pii-model-compare",
        description="ko-pii vs HF privacy model comparison",
    )
    p.add_argument("path", help="Input file (text corpus OR KDPII gold JSON)")
    p.add_argument("--mode", choices=["pseudo-gt", "kdpii"], default="pseudo-gt",
                   help="pseudo-gt: HF output as pseudo-GT vs ko-pii. "
                        "kdpii: both vs real KDPII gold labels.")
    p.add_argument("--model", default="openai/privacy-filter",
                   help="HF model id")
    p.add_argument("--backend", default="auto", choices=["auto", "torch", "onnx"])
    p.add_argument("--device", default=None, choices=[None, "cuda", "cpu", "dml"])
    p.add_argument("--max-docs", type=int, default=None)
    p.add_argument("--cache-dir", default="./models")
    p.add_argument("--person-min-length", type=int, default=3)
    args = p.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"파일 없음: {path}", file=sys.stderr)
        return 1

    if args.mode == "kdpii":
        print(f"평가 모드: KDPII gold 3-way ({path})", file=sys.stderr)
        reports = run_kdpii_three_way(
            path, gt_model_id=args.model, backend=args.backend,
            max_docs=args.max_docs, person_min_length=args.person_min_length,
            cache_dir=args.cache_dir,
        )
        print(format_kdpii_threeway(reports))
    else:
        docs = _read_documents(path)
        if args.max_docs:
            docs = docs[: args.max_docs]
        label = path.name
        print(f"평가 모드: pseudo-GT, {len(docs)} 문서", file=sys.stderr)
        report = run_comparison(docs, gt_model_id=args.model, corpus_label=label)
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
