"""KLUE-NER 한국어 NER 벤치마크 어댑터.

KLUE benchmark (https://github.com/KLUE-benchmark/KLUE) 의 NER 서브셋:
- 자연어 신문기사 문장 단위
- 6 entity types: PS (사람), OG (기관), LC (장소), DT (날짜), TI (시간), QT (수량)
- 32K training + 5K dev samples
- BIO 캐릭터-단위 태깅

본 모듈은 ko-pii 의 ``PERSON`` 검출을 KLUE-NER 의 ``PS`` 라벨에 대해 평가한다.

주의:
- KLUE-NER PS 는 *모든 인명* 포함 (역사인물·외국인·정치인 등)
- ko-pii PERSON 은 *한국 공공 도메인 가명화 대상*  — 역사인물·정치인 같은 공인은
  엄밀히는 PII 가 아님 (공개 정보)
- 따라서 본 평가는 *자연어 PERSON recall* 의 어림짐작용 — 정밀도가 낮게
  나오더라도 그것이 곧 production 정확도 저하를 의미하지 않음

사용:
    from ko_pii.eval.klue_ner import load_klue_ner, evaluate_person

    sentences = load_klue_ner("klue-ner-v1.1_dev.tsv")
    report = evaluate_person(sentences)
    print(report)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator


@dataclass
class NerSpan:
    label: str
    start: int
    end: int
    text: str


@dataclass
class NerSentence:
    text: str
    spans: list[NerSpan] = field(default_factory=list)


def _parse_chars_and_tags(lines: Iterator[str]) -> Iterator[NerSentence]:
    """KLUE-NER 줄 단위 (CHAR \\t TAG) → 문장 단위 변환.

    문장 구분: 빈 줄.
    헤더: ``## `` 로 시작 — 무시.
    """
    chars: list[str] = []
    tags: list[str] = []

    def _flush() -> NerSentence | None:
        if not chars:
            return None
        text = "".join(chars)
        spans = _bio_to_spans(text, chars, tags)
        return NerSentence(text=text, spans=spans)

    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("##"):
            continue
        if not line.strip():
            sent = _flush()
            if sent is not None:
                yield sent
            chars, tags = [], []
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ch, tag = parts[0], parts[1]
        chars.append(ch)
        tags.append(tag)

    sent = _flush()
    if sent is not None:
        yield sent


def _bio_to_spans(text: str, chars: list[str], tags: list[str]) -> list[NerSpan]:
    spans: list[NerSpan] = []
    i = 0
    n = len(tags)
    while i < n:
        tag = tags[i]
        if tag.startswith("B-"):
            label = tag[2:]
            start = i
            i += 1
            while i < n and tags[i] == f"I-{label}":
                i += 1
            end = i
            spans.append(NerSpan(
                label=label,
                start=start,
                end=end,
                text="".join(chars[start:end]),
            ))
        else:
            i += 1
    return spans


def load_klue_ner(path: str) -> list[NerSentence]:
    """KLUE-NER 파일을 문장 리스트로 로드."""
    with open(path, "r", encoding="utf-8") as f:
        return list(_parse_chars_and_tags(f))


# ─────────────────────────────────────────────────────────────────────
# 평가
# ─────────────────────────────────────────────────────────────────────

@dataclass
class NerEvalReport:
    label: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    sentence_count: int = 0

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

    def format(self) -> str:
        return (
            f"[KLUE-NER {self.label}]  문장 {self.sentence_count}건  "
            f"TP={self.tp}  FP={self.fp}  FN={self.fn}\n"
            f"  Precision = {self.precision:.3f}\n"
            f"  Recall    = {self.recall:.3f}\n"
            f"  F1        = {self.f1:.3f}"
        )


def evaluate_person(
    sentences: Iterable[NerSentence],
    mode: str = "partial",
    sample_limit: int | None = None,
    fullname_only: bool = True,
    korean_only: bool = False,
) -> NerEvalReport:
    """ko-pii PERSON 검출을 KLUE-NER PS 라벨에 대해 평가.

    ``mode``:
      - ``"partial"`` : span 겹침 = TP (오프셋 차이 허용)
      - ``"strict"``  : 정확 일치
    ``fullname_only`` : True 면 *한글 2자+ 풀네임* 만 gold 로 인정.
      - 1자 단독 성씨 ("박", "김") — PII 아님 (확실성 부족)
      - 영문 1자 ("A", "B") — 이미 가명화된 표기
      - 외래어·외국인명 (알파치노, 저우쉰 등) — 한국 공공 가명화 대상 아님
      → 본 라이브러리의 *현실적* 평가 대상에 맞춤.
    """
    from ko_pii.patterns.person import detect as detect_person

    report = NerEvalReport(label="PERSON")
    sentences_list = list(sentences)
    if sample_limit:
        sentences_list = sentences_list[:sample_limit]

    def _is_valid_korean_fullname(text: str) -> bool:
        if not fullname_only:
            return True
        if len(text) < 3 or len(text) > 5:  # 풀네임 = 3-5자 (단성/외자 제외)
            return False
        if not all("가" <= ch <= "힣" for ch in text):
            return False
        if korean_only:
            # Method 7: 한국 이름만 평가 (외국인명 제외)
            from ko_pii.context.name_origin import classify_name_origin
            return classify_name_origin(text) == "korean"
        return True

    for sent in sentences_list:
        report.sentence_count += 1
        gold_persons = [
            s for s in sent.spans
            if s.label == "PS" and _is_valid_korean_fullname(s.text)
        ]
        predicted_raw = list(detect_person(sent.text))
        # korean_only 모드면 외국인 origin 검출도 평가에서 제외
        if korean_only:
            predicted = [
                p for p in predicted_raw
                if p.extra.get("origin") != "foreign"
            ]
        else:
            predicted = predicted_raw

        matched_pred: set[int] = set()
        for g in gold_persons:
            hit = -1
            for i, p in enumerate(predicted):
                if i in matched_pred:
                    continue
                if mode == "strict":
                    if p.start == g.start and p.end == g.end:
                        hit = i
                        break
                else:
                    if p.start < g.end and g.start < p.end:
                        hit = i
                        break
            if hit >= 0:
                report.tp += 1
                matched_pred.add(hit)
            else:
                report.fn += 1
        for i, p in enumerate(predicted):
            if i in matched_pred:
                continue
            # FP 도 *한글 풀네임* 기준에 맞춰 필터
            if _is_valid_korean_fullname(p.text):
                report.fp += 1

    return report


def sample_errors(
    sentences: Iterable[NerSentence],
    error_type: str = "fn",
    limit: int = 10,
) -> list[tuple[NerSentence, list[str]]]:
    """오류 사례 샘플 — FN/FP 분석용.

    error_type: ``"fn"`` (gold 인데 못 잡음) / ``"fp"`` (잘못 잡음).
    """
    from ko_pii.patterns.person import detect as detect_person
    out = []
    for sent in sentences:
        gold_persons = [s for s in sent.spans if s.label == "PS"]
        predicted = list(detect_person(sent.text))
        if error_type == "fn":
            for g in gold_persons:
                hit = any(p.start < g.end and g.start < p.end for p in predicted)
                if not hit:
                    out.append((sent, [g.text]))
                    if len(out) >= limit:
                        return out
        else:  # fp
            for p in predicted:
                hit = any(p.start < g.end and g.start < p.end
                          for g in gold_persons)
                if not hit:
                    out.append((sent, [p.text]))
                    if len(out) >= limit:
                        return out
    return out
