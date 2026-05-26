"""네이버 x 창원대 NER 데이터로 ko-pii / openai/privacy-filter PERSON 평가.

데이터: Korpora naver_changwon_ner (90,000 문장, PER_B/PER_I 태깅)
방법: KLUE-NER 과 동일 — 한글 풀네임 (3-5자) 만 비교, partial overlap

라벨 매핑:
  PER_B/PER_I → PERSON (연속 토큰 연결)
  LOC_B/LOC_I → ADDRESS (참고)
  나머지 (ORG/DAT/NUM/CVL/EVT 등) → ko-pii 매핑 없음 (PII 아님)

CLI:
  python data/eval_naver_changwon_ner.py                 # ko-pii, 90K 전체
  python data/eval_naver_changwon_ner.py 10000           # ko-pii, 10K 샘플
  python data/eval_naver_changwon_ner.py --openai        # openai/privacy-filter, 90K
  python data/eval_naver_changwon_ner.py 10000 --openai  # openai, 10K 샘플
"""
from __future__ import annotations

import argparse
import sys
import time

from Korpora import Korpora


def _is_korean_fullname(text: str, korean_only: bool = True) -> bool:
    t = text.strip()
    if len(t) < 3 or len(t) > 5:
        return False
    if not all("가" <= ch <= "힣" for ch in t):
        return False
    if korean_only:
        from ko_pii.context.name_origin import classify_name_origin
        return classify_name_origin(t) == "korean"
    return True


def extract_per_spans(words: list[str], tags: list[str]) -> list[tuple[int, int, str]]:
    """BIO 태깅에서 PER span 추출. (start_char, end_char, text) 반환."""
    spans = []
    text = " ".join(words)

    cursor = 0
    positions = []
    for w in words:
        idx = text.find(w, cursor)
        positions.append((idx, idx + len(w)))
        cursor = idx + len(w)

    i = 0
    while i < len(tags):
        if tags[i] == "PER_B":
            start = positions[i][0]
            end = positions[i][1]
            parts = [words[i]]
            j = i + 1
            while j < len(tags) and tags[j] == "PER_I":
                end = positions[j][1]
                parts.append(words[j])
                j += 1
            name = "".join(parts)
            # 조사 제거 (은/는/이/가/을/를/의/에/와/과/도/로)
            for suffix in ["은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "에게"]:
                if name.endswith(suffix) and len(name) > len(suffix) + 2:
                    name = name[:-len(suffix)]
                    break
            spans.append((start, end, name))
            i = j
        else:
            i += 1
    return spans


def _run_kpii(sentences) -> tuple[int, int, int, float]:
    """ko-pii rule-based detector PERSON 평가."""
    from ko_pii.detect import detect_all

    tp = fp = fn = 0
    t0 = time.time()

    for i, ex in enumerate(sentences):
        text = " ".join(ex.words)
        gold_per = extract_per_spans(ex.words, ex.tags)
        gold_per = [(s, e, t) for s, e, t in gold_per if _is_korean_fullname(t)]

        detections = [r for r in detect_all(text) if r.label == "PERSON"]
        det_per = [(r.start, r.end, r.text) for r in detections
                   if _is_korean_fullname(r.text)]

        gold_matched = set()
        det_matched = set()

        for di, (ds, de, dt) in enumerate(det_per):
            for gi, (gs, ge, gt) in enumerate(gold_per):
                if not (de <= gs or ds >= ge):
                    gold_matched.add(gi)
                    det_matched.add(di)

        tp += len(gold_matched)
        fn += len(gold_per) - len(gold_matched)
        fp += len(det_per) - len(det_matched)

        if (i + 1) % 10000 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(sentences)} ({elapsed:.0f}s)", file=sys.stderr)

    return tp, fp, fn, time.time() - t0


def _run_openai(sentences, *, cache_dir: str = "./models", device: str = "cpu",
                onnx_file: str = "onnx/model_q4f16.onnx") -> tuple[int, int, int, float]:
    """openai/privacy-filter (ONNX) PERSON 평가 — KLUE-NER 와 동일 로직.

    ko-pii eval 인터페이스와 *별도* 로, 직접 ``Span.label == "private_person"`` 만
    필터링 (다른 ML 모델과 한 번도 함수 통일 안 한 이유는 라벨 prefix 차이 때문).
    """
    from ko_pii.eval.model_comparison import HFPrivacyDetector

    detector = HFPrivacyDetector(
        "openai/privacy-filter",
        backend="onnx",
        device=device,
        cache_dir=cache_dir,
        onnx_file=onnx_file,
    )
    print(f"  device: {detector.device}", file=sys.stderr)

    tp = fp = fn = 0
    t0 = time.time()

    for i, ex in enumerate(sentences):
        text = " ".join(ex.words)
        gold_per = extract_per_spans(ex.words, ex.tags)
        gold_per = [(s, e, t) for s, e, t in gold_per if _is_korean_fullname(t)]

        raw_pred = detector.detect(text)
        det_per = [
            (p.start, p.end, p.text)
            for p in raw_pred
            if p.label == "private_person"
            and _is_korean_fullname(p.text.strip() if p.text else "")
        ]

        gold_matched = set()
        det_matched = set()
        for di, (ds, de, dt) in enumerate(det_per):
            for gi, (gs, ge, gt) in enumerate(gold_per):
                if not (de <= gs or ds >= ge):
                    gold_matched.add(gi)
                    det_matched.add(di)

        tp += len(gold_matched)
        fn += len(gold_per) - len(gold_matched)
        fp += len(det_per) - len(det_matched)

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0.0
            print(f"  {i+1}/{len(sentences)} ({elapsed:.0f}s, {rate:.1f} sent/sec)",
                  file=sys.stderr)

    return tp, fp, fn, time.time() - t0


def main():
    p = argparse.ArgumentParser(
        prog="eval_naver_changwon_ner",
        description="네이버 x 창원대 NER 에서 ko-pii / openai/PF PERSON F1 측정",
    )
    p.add_argument("limit", type=int, nargs="?", default=None,
                   help="문장 샘플 수 (생략 시 90,000 전체)")
    p.add_argument("--openai", action="store_true",
                   help="ko-pii 대신 openai/privacy-filter 평가")
    p.add_argument("--cache-dir", default="./models",
                   help="HF 모델 캐시 디렉토리 (openai 모드)")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "dml"],
                   help="ONNX EP 선택 (openai 모드)")
    p.add_argument("--onnx-file", default="onnx/model_q4f16.onnx",
                   help="openai/PF ONNX 파일 (기본 quantized q4f16)")
    args = p.parse_args()

    print("Loading naver_changwon_ner...", file=sys.stderr)
    corpus = Korpora.load("naver_changwon_ner")

    sentences = list(corpus.train)
    if args.limit:
        sentences = sentences[: args.limit]
    print(f"Sentences: {len(sentences)}", file=sys.stderr)

    if args.openai:
        engine = "openai/privacy-filter (ONNX)"
        tp, fp, fn, elapsed = _run_openai(
            sentences,
            cache_dir=args.cache_dir,
            device=args.device,
            onnx_file=args.onnx_file,
        )
    else:
        engine = "ko-pii (rules)"
        tp, fp, fn, elapsed = _run_kpii(sentences)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n=== {engine} on naver_changwon_ner (PERSON, korean_only=True) ===")
    print(f"  Sentences: {len(sentences)}")
    print(f"  TP={tp}  FP={fp}  FN={fn}")
    print(f"  Precision = {precision:.3f}")
    print(f"  Recall    = {recall:.3f}")
    print(f"  F1        = {f1:.3f}")
    rate = len(sentences) / elapsed if elapsed > 0 else 0.0
    print(f"  Time: {elapsed:.1f}s ({rate:.0f} sent/sec)")


if __name__ == "__main__":
    main()
