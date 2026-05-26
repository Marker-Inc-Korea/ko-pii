"""실제 행정문서 본문 (AI Hub 569) 에 합성 PII 를 주입해 평가 코퍼스 생성.

배경: 기존 합성 코퍼스 (`ko_pii.eval.synth`) 는 13 템플릿 기반이라 양쪽 검출기가
정형 anchor 에 *과적합* 될 수 있음. 본 스크립트는:
  1. AI Hub 569 행정문서 (data/corpus/aihub_569/) 의 *실제 한국 공공 텍스트*
     문단을 base 로 사용 (양 모델 다 못 본 데이터)
  2. 알려진 위치에 PII 를 주입 — gold span 100% 정확
  3. 다양한 anchor 패턴 (필드 라벨 / 조사 / 괄호 주석 / 본문 inline) 으로
     주입해 *anchor 다양성 자연 증대*

출력: JSONL — 한 줄당 ``{"text": "...", "spans": [{"label", "start", "end",
"text"}, ...]}``.

평가 호환: `data/eval_injected_corpus.py` 가 이 JSONL 을 ``GoldDocument`` 리스트로
로드해 ``ko_pii.eval.metrics.score_corpus`` 에 그대로 흘림.

PII 풀: `ko_pii.eval.synth` 의 검증된 (체크섬 valid) 값 + 추가.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Iterator

# 검증된 PII 풀 — synth.py 의 손계산 valid 값 재사용
from ko_pii.eval.synth import (
    _BIZREG_SAMPLES,
    _NAMES,
    _PHONE_LANDLINE,
    _PHONE_MOBILE,
    _RRN_SAMPLES,
)


# ─────────────────────────────────────────────────────────────────────
# PII 풀 — 확장
# ─────────────────────────────────────────────────────────────────────

EMAIL_LOCALS = [
    "minjeon", "kim.cs", "jiwon.lee", "park.dr", "complaint",
    "info", "minwon", "admin", "support", "hong.gd",
    "min.civic", "cs.team", "jhpark", "ksy_kim",
]
EMAIL_DOMAINS = [
    "korea.kr", "go.kr", "gov.kr", "seoul.go.kr", "gyeonggi.go.kr",
    "naver.com", "daum.net", "gmail.com", "kakao.com",
]

# 도로명 주소 풀 (서울/경기/지방 분포)
ADDRESSES = [
    "서울특별시 강남구 테헤란로 123",
    "서울특별시 종로구 세종대로 209",
    "서울특별시 영등포구 여의대로 70",
    "서울특별시 마포구 마포대로 144",
    "경기도 성남시 분당구 분당대로 88",
    "경기도 수원시 영통구 광교산로 154-42",
    "부산광역시 해운대구 센텀남대로 35",
    "대전광역시 유성구 대학로 99",
    "광주광역시 서구 상무중앙로 7",
    "인천광역시 연수구 미래로 7",
    "강원도 춘천시 중앙로 1",
    "세종특별자치시 도움5로 19",
]

# 차량번호 풀 (신형 NN[가나다]NNNN)
VEHICLES = [
    "12가3456", "34나5678", "56다7890", "78라1234",
    "98마5432", "11바9876", "22사6543", "33아2109",
    "123가4567", "456나7890",  # 3-digit prefix
]

# 운전면허번호 풀 (12자리, region 11~28)
DRIVER_LICENSES = [
    "11-90-123456-78", "12-95-654321-09", "13-00-111222-33",
    "23-15-987654-32", "28-22-100000-50",
]

# 여권번호 풀
PASSPORTS = ["M12345678", "S87654321", "D11223344", "G55667788"]

# 다양한 직책 (PERSON anchor 강화용)
TITLES = [
    "주임", "대리", "과장", "차장", "부장", "팀장", "실장", "국장",
    "장관", "차관", "시장", "구청장", "도지사", "처장",
    "주무관", "사무관", "서기관", "이사관",
    "담당자", "책임자", "신청인", "민원인",
]


def _make_email(rnd: random.Random) -> str:
    return f"{rnd.choice(EMAIL_LOCALS)}@{rnd.choice(EMAIL_DOMAINS)}"


def _make_account(rnd: random.Random) -> str:
    """간단한 계좌번호 (3-2-6 or 14-digit). 키워드 anchor 와 함께 사용."""
    parts = [
        f"{rnd.randrange(100, 1000)}",
        f"{rnd.randrange(10, 100)}",
        f"{rnd.randrange(100000, 1000000)}",
    ]
    return "-".join(parts)


# ─────────────────────────────────────────────────────────────────────
# 주입 전략 — 다양한 anchor 패턴
# ─────────────────────────────────────────────────────────────────────


def _strategy_field_label(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """필드 라벨 패턴: '신청인: 김민수 / 연락처: 010-1234-5678'"""
    name = rnd.choice(_NAMES)
    phone = rnd.choice(_PHONE_MOBILE)
    label_n = rnd.choice(["신청인", "민원인", "담당자", "보고자", "처리자"])
    label_p = rnd.choice(["연락처", "전화번호", "핸드폰", "전화"])
    snippet = f"{label_n}: {name} / {label_p}: {phone}"
    spans = [("PERSON", name), ("PHONE", phone)]
    return snippet, spans


def _strategy_signature(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """문서 끝 서명: '— 보고자 박철수 (010-9876-5432)'"""
    name = rnd.choice(_NAMES)
    phone = rnd.choice(_PHONE_MOBILE + _PHONE_LANDLINE)
    role = rnd.choice(["보고자", "기안자", "검토자", "결재자"])
    snippet = f"— {role} {name} ({phone})"
    return snippet, [("PERSON", name), ("PHONE", phone)]


def _strategy_full_application(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """본격 양식: 성명 + 주민번호 + 주소 + 전화"""
    name = rnd.choice(_NAMES)
    rrn = rnd.choice(_RRN_SAMPLES)
    addr = rnd.choice(ADDRESSES)
    phone = rnd.choice(_PHONE_MOBILE)
    snippet = (
        f"성명: {name}\n주민등록번호: {rrn}\n주소: {addr}\n연락처: {phone}"
    )
    return snippet, [
        ("PERSON", name), ("RRN", rrn),
        ("ADDRESS", addr), ("PHONE", phone),
    ]


def _strategy_inline_parenthetical(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """본문 inline 괄호: '...{ 김민수 주임 }께서 ...' 또는 '(010-1234-5678)'"""
    if rnd.random() < 0.5:
        name = rnd.choice(_NAMES)
        title = rnd.choice(TITLES)
        snippet = f" ({name} {title})"
        return snippet, [("PERSON", name)]
    else:
        phone = rnd.choice(_PHONE_MOBILE)
        snippet = f" (문의: {phone})"
        return snippet, [("PHONE", phone)]


def _strategy_subject_with_title(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """직책 anchor 인접: '김민수 과장이' / '박철수 주임이며'"""
    name = rnd.choice(_NAMES)
    title = rnd.choice(TITLES)
    particle = rnd.choice(["가", "이", "께서", "은", "는"])
    if particle in ("이", "은"):
        if not (0xAC00 <= ord(name[-1]) <= 0xD7A3) or (ord(name[-1]) - 0xAC00) % 28 == 0:
            particle = {"이": "가", "은": "는"}[particle]
    snippet = f" {name} {title}{particle} "
    return snippet, [("PERSON", name)]


def _strategy_email_contact(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """이메일 + 사이트 contact 라인"""
    email = _make_email(rnd)
    snippet = f" (문의 이메일: {email})"
    return snippet, [("EMAIL", email)]


def _strategy_business_party(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """사업자/공급자 라인: '공급자: 한전 (사업자번호 120-81-47521)'"""
    bizreg = rnd.choice(_BIZREG_SAMPLES)
    role = rnd.choice(["공급자", "수급자", "납품업체", "사업자"])
    snippet = f"{role} (사업자번호 {bizreg})"
    return snippet, [("BUSINESS_REG", bizreg)]


def _strategy_account(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """계좌번호 anchor"""
    acc = _make_account(rnd)
    name = rnd.choice(_NAMES)
    snippet = f" 입금 계좌: {acc} (예금주: {name})"
    return snippet, [("ACCOUNT", acc), ("PERSON", name)]


def _strategy_vehicle(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """차량번호"""
    plate = rnd.choice(VEHICLES)
    snippet = f" (차량번호 {plate})"
    return snippet, [("VEHICLE", plate)]


def _strategy_driver_passport(rnd: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """운전면허 또는 여권번호"""
    if rnd.random() < 0.5:
        dl = rnd.choice(DRIVER_LICENSES)
        snippet = f" (운전면허번호: {dl})"
        return snippet, [("DRIVER_LICENSE", dl)]
    else:
        psp = rnd.choice(PASSPORTS)
        snippet = f" (여권번호: {psp})"
        return snippet, [("PASSPORT", psp)]


# 각 전략과 base 확률
_STRATEGIES = [
    (_strategy_field_label, 0.20),
    (_strategy_signature, 0.15),
    (_strategy_full_application, 0.10),
    (_strategy_inline_parenthetical, 0.18),
    (_strategy_subject_with_title, 0.15),
    (_strategy_email_contact, 0.06),
    (_strategy_business_party, 0.06),
    (_strategy_account, 0.04),
    (_strategy_vehicle, 0.03),
    (_strategy_driver_passport, 0.03),
]


def _pick_strategy(rnd: random.Random):
    r = rnd.random()
    acc = 0.0
    for fn, p in _STRATEGIES:
        acc += p
        if r < acc:
            return fn
    return _STRATEGIES[-1][0]


# ─────────────────────────────────────────────────────────────────────
# 코퍼스 빌더
# ─────────────────────────────────────────────────────────────────────


def _redact_existing_pii(text: str) -> str:
    """ko-pii 가 감지한 모든 기존 PII 를 길이-보존 placeholder 로 치환.

    Eval 디자인 문제 해결: base text 에 실제 PII (행정문서에 나오는 장관/공무원
    이름 등) 가 있으면 gold 없이 두 검출기 모두 FP 로 잡힘. 사전 sanitize 로
    base 의 PII 를 *모두 제거* → 주입된 PII 만 gold 로 명확히 평가.

    한계: ko-pii 자체가 미탐인 PII 는 그대로 남음 → openai 가 그걸 잡으면 FP.
    이는 알려진 잔존 노이즈 (단, 본 코퍼스는 행정문서 본문이라 PII 분포 낮음).
    """
    from ko_pii.detect import detect_all

    detections = sorted(detect_all(text), key=lambda r: r.start, reverse=True)
    out = text
    for r in detections:
        n = len(r.text)
        if r.label == "PERSON":
            placeholder = "○" * n
        elif r.label in ("PHONE", "RRN", "FRN", "CARD", "ACCOUNT",
                         "BUSINESS_REG", "CORP_REG", "PASSPORT",
                         "DRIVER_LICENSE", "VEHICLE", "MEDICAL_INSURANCE",
                         "POSTAL_CODE", "IP"):
            placeholder = "X" * n
        elif r.label in ("EMAIL", "URL"):
            placeholder = "@" * n
        elif r.label == "ADDRESS":
            placeholder = "△" * n
        else:
            placeholder = "●" * n
        out = out[:r.start] + placeholder + out[r.end:]
    return out


def _load_base_paragraphs(max_existing_pii: int = 5) -> list[str]:
    """data/corpus/aihub_569/*.txt 에서 문단 추출 + 사전 PII 제거.

    1. 모든 .txt 파일에서 \\n\\n 분할로 문단 추출
    2. 길이 200-2000자 사이만 (너무 짧으면 anchor 의미 없음, 너무 길면 처리 ↓)
    3. ko-pii 가 detect 한 PII 가 ``max_existing_pii`` 개 이상이면 *제외*
       (PII-rich 문단은 인젝션 평가에 노이즈)
    4. 남은 PII 는 placeholder 로 redact
    """
    from ko_pii.detect import detect_all

    root = Path(__file__).parent / "corpus" / "aihub_569"
    paras: list[str] = []
    skipped_too_pii = 0
    for f in sorted(root.glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        for block in text.split("\n\n"):
            b = block.strip()
            if not (200 <= len(b) <= 2000):
                continue
            if "\n" in b[:200]:
                continue
            existing_count = sum(1 for _ in detect_all(b))
            if existing_count > max_existing_pii:
                skipped_too_pii += 1
                continue
            paras.append(_redact_existing_pii(b))
    print(f"  base paragraphs: {len(paras)} (filtered out {skipped_too_pii} PII-rich)")
    return paras


def _inject_into(base_text: str, rnd: random.Random,
                 n_strategies: int) -> tuple[str, list[dict]]:
    """base_text 에 n_strategies 개의 PII snippet 을 주입하고 gold span 기록."""
    sentences = base_text.split(". ")
    if len(sentences) < 2:
        sentences = [base_text]

    spans_record: list[dict] = []
    used_strategies = set()
    snippets_to_insert: list[tuple[int, str, list[tuple[str, str]]]] = []
    # 삽입 위치 무작위 (sentence boundary 또는 앞/뒤)
    for _ in range(n_strategies):
        # avoid duplicate strategy in same doc — improves variety
        for _ in range(10):
            fn = _pick_strategy(rnd)
            if fn not in used_strategies or len(used_strategies) >= 5:
                used_strategies.add(fn)
                break
        snippet, pii_list = fn(rnd)
        pos = rnd.randint(0, len(sentences))  # 어느 문장 사이/앞/뒤
        snippets_to_insert.append((pos, snippet, pii_list))

    # 위치 정렬 — sentence boundary 기준
    snippets_to_insert.sort(key=lambda x: x[0])

    out_parts: list[str] = []
    pii_text_to_find: list[tuple[str, str]] = []
    cursor = 0
    snippet_idx = 0
    for sent_idx in range(len(sentences) + 1):
        # 이 위치에 삽입할 snippet 처리
        while (snippet_idx < len(snippets_to_insert)
               and snippets_to_insert[snippet_idx][0] == sent_idx):
            _, snip, plist = snippets_to_insert[snippet_idx]
            sep = "\n\n" if sent_idx in (0, len(sentences)) else " "
            out_parts.append(sep + snip + sep)
            for label, form in plist:
                pii_text_to_find.append((label, form))
            snippet_idx += 1
        # 문장 추가
        if sent_idx < len(sentences):
            if out_parts and not out_parts[-1].endswith(" ") and not sentences[sent_idx].startswith(" "):
                out_parts.append(" ")
            out_parts.append(sentences[sent_idx])
            if sent_idx < len(sentences) - 1:
                out_parts.append(". ")
    final = "".join(out_parts).strip()

    # gold span 위치 계산 — 각 PII form 의 마지막 등장 위치 (앞에 있을 수도 있으니 last) 가 아니라 가장 처음 등장 (rule: inject 한 form 은 base text 에 없다 가정)
    # 만약 base text 에 이미 같은 문자열이 있으면 첫 등장이 base 의 것 → 가장 신뢰 가능한 건 다음:
    # 처음 등장하는 form 위치를 spans 에 기록 (대부분 inject 가 first occurrence)
    seen_starts: dict[str, list[int]] = {}
    for label, form in pii_text_to_find:
        starts = seen_starts.setdefault(form, [])
        search_from = max(starts) + 1 if starts else 0
        idx = final.find(form, search_from)
        if idx < 0:
            # 못 찾으면 skip (extreme edge case)
            continue
        starts.append(idx)
        spans_record.append({
            "label": label,
            "start": idx,
            "end": idx + len(form),
            "text": form,
        })
    return final, spans_record


def generate_corpus(n: int, seed: int = 0,
                    pii_per_doc: tuple[int, int] = (2, 4)) -> Iterator[dict]:
    """``n`` 개 문서 생성 — 각 문서는 ``{"text", "spans"}`` dict."""
    rnd = random.Random(seed)
    paras = _load_base_paragraphs()
    if not paras:
        raise RuntimeError("Base paragraphs not found in data/corpus/aihub_569/")
    print(f"Base paragraphs available: {len(paras)}")

    base_indices = rnd.sample(
        range(len(paras)), min(n, len(paras))
    )
    if n > len(paras):
        # 부족하면 with replacement
        extra = [rnd.randrange(len(paras)) for _ in range(n - len(paras))]
        base_indices.extend(extra)

    for bi in base_indices:
        base = paras[bi]
        n_strats = rnd.randint(*pii_per_doc)
        text, spans = _inject_into(base, rnd, n_strats)
        yield {"text": text, "spans": spans}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-n", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", default="data/corpus/injected_pii_corpus.jsonl")
    args = p.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    total_spans = 0
    label_counts: dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as f:
        for doc in generate_corpus(args.n, seed=args.seed):
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
            count += 1
            total_spans += len(doc["spans"])
            for s in doc["spans"]:
                label_counts[s["label"]] = label_counts.get(s["label"], 0) + 1
    print(f"\n{count} docs / {total_spans} gold spans → {out_path}")
    print("라벨 분포:")
    for label in sorted(label_counts):
        print(f"  {label}: {label_counts[label]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
