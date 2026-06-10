#!/usr/bin/env python3
"""외부 검증셋 v2 — OOD 도메인 + 체크섬 유효 ID + 신규 anchor 패턴.

기존 injected_pii_corpus.jsonl(aihub_569·anchor 10종·체크섬 무효 ID 다수)의
세 가지 한계를 고친 2세대 외부 평가셋:

  1. **base 도메인 교체**: aihub_71845(공공 민원 상담) — 기존 주입 코퍼스가
     쓰지 않은 도메인. 학습데이터(KDPII 대화체·생성 행정체)와도 다름.
  2. **ID 전부 체크섬 유효**: ko_pii.checksum 의 compute_check_digit 로 역생성
     (RRN·CARD(실존 BIN)·사업자·법인). 기존 평가셋들의 "형식만 맞는 가짜 번호"
     아티팩트(룰 부당 처벌 / ML 가짜분포 학습 이득)를 제거.
  3. **anchor 8종 신규**: v1 의 10종 템플릿 미재사용 — self-fulfilling 차단.

모든 주입 값은 중립 문맥에서 detect_all 로 검출 가능성을 사후검증해 gold 품질을
보장한다(검출 불가능한 값이 gold 에 들어가 FN 을 강제하는 일 방지 — 단 이는
"룰이 잡을 수 있는 형식"만 넣는다는 뜻이며, 문맥 anchor 는 전략별로 상이).

usage: python data/build_external_eval_v2.py [--n 400] [--seed 42]
출력: data/corpus/external_inject_v2.jsonl  {"text", "spans":[{label,start,end,text}]}
"""
from __future__ import annotations

import argparse, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data"))

from ko_pii.checksum import rrn_checksum, business_reg_checksum, corp_reg_checksum, luhn
from ko_pii.detect import detect_all
from ko_pii.eval.synth import (_NAMES, _ADDR_ROAD, _ADDR_JIBUN, _TITLES_GOV_POOL,
                               _AGENCIES_POOL, _DEPT_POOL, _EMAIL_SAMPLES)
from inject_pii_corpus import _redact_existing_pii

_BANKS = ["국민은행", "신한은행", "우리은행", "하나은행", "농협은행", "우체국"]


# ── 체크섬 유효 ID 생성 (+ 검출 가능성 사후검증) ─────────────────
def _verify(label: str, value: str, ctx: str) -> bool:
    return any(r.label == label and r.text.replace(" ", "") == value.replace(" ", "")
               for r in detect_all(ctx))


def gen_rrn(rnd: random.Random, spaced: bool = False) -> str:
    while True:
        y, m, d = rnd.randint(55, 99), rnd.randint(1, 12), rnd.randint(1, 28)
        base12 = f"{y:02d}{m:02d}{d:02d}{rnd.choice('12')}{rnd.randrange(0, 100000):05d}"
        chk = rrn_checksum.compute_check_digit(base12)
        sep = " - " if spaced else "-"
        v = f"{base12[:6]}{sep}{base12[6:]}{chk}"
        if _verify("RRN", v, f"주민등록번호 {v} 확인"):
            return v


def gen_card(rnd: random.Random) -> str:
    while True:
        payload = rnd.choice("459") + "".join(rnd.choice("0123456789") for _ in range(14))
        num = payload + str(luhn.compute_check_digit(payload))
        v = "-".join([num[0:4], num[4:8], num[8:12], num[12:16]])
        if _verify("CARD", v, f"카드번호 {v} 결제"):
            return v


def gen_bizreg(rnd: random.Random) -> str:
    while True:
        nine = "".join(rnd.choice("0123456789") for _ in range(9))
        num = nine + str(business_reg_checksum.compute_check_digit(nine))
        v = f"{num[:3]}-{num[3:5]}-{num[5:]}"
        if _verify("BUSINESS_REG", v, f"사업자등록번호 {v} 기재"):
            return v


def gen_corpreg(rnd: random.Random) -> str:
    while True:
        twelve = "".join(rnd.choice("0123456789") for _ in range(12))
        num = twelve + str(corp_reg_checksum.compute_check_digit(twelve))
        v = f"{num[:6]}-{num[6:]}"
        if _verify("CORP_REG", v, f"법인등록번호 {v} 등기"):  # RRN 양보 충돌은 여기서 걸러짐
            return v


def gen_phone(rnd: random.Random) -> str:
    return f"010-{rnd.randrange(2000, 10000)}-{rnd.randrange(1000, 10000)}"


def gen_account(rnd: random.Random) -> str:
    return f"{rnd.randrange(100, 1000)}-{rnd.randrange(10, 100)}-{rnd.randrange(100000, 1000000)}"


# ── 신규 anchor 전략 8종 (v1 의 10종과 비중복) ────────────────────
# 각 전략은 (snippet, [(label, value), ...]) 반환. 값은 snippet 에 정확히 1회 등장.
def s_colon_form_spaced(rnd):
    name, rrn = rnd.choice(_NAMES), gen_rrn(rnd, spaced=True)
    return (f"성    명 : {name}\n주민등록번호 : {rrn}",
            [("PERSON", name), ("RRN", rrn)])


def s_complaint_sentence(rnd):
    name, phone = rnd.choice(_NAMES), gen_phone(rnd)
    return (f"민원인 {name}이 제기한 위 사안의 처리 결과는 {phone}으로 회신될 예정입니다.",
            [("PERSON", name), ("PHONE", phone)])


def s_footer_contact(rnd):
    dept, title, name = rnd.choice(_DEPT_POOL), rnd.choice(_TITLES_GOV_POOL), rnd.choice(_NAMES)
    phone, email = gen_phone(rnd), rnd.choice(_EMAIL_SAMPLES)
    return (f"담당: {dept} {title} {name} (연락처 {phone}, 전자우편 {email})",
            [("POSITION", title), ("PERSON", name), ("PHONE", phone), ("EMAIL", email)])


def s_list_items(rnd):
    name, rrn, addr = rnd.choice(_NAMES), gen_rrn(rnd), rnd.choice(_ADDR_ROAD)
    return (f"- 신청인: {name}\n- 주민등록번호: {rrn}\n- 주소: {addr}",
            [("PERSON", name), ("RRN", rrn), ("ADDRESS", addr)])


def s_corp_party(rnd):
    corp, biz, name = gen_corpreg(rnd), gen_bizreg(rnd), rnd.choice(_NAMES)
    agency = rnd.choice(_AGENCIES_POOL)
    return (f"{agency}에 등록된 법인(법인등록번호 {corp}, 사업자등록번호 {biz}, 대표자 {name})의 신고 내역입니다.",
            [("CORP_REG", corp), ("BUSINESS_REG", biz), ("PERSON", name)])


def s_payment_line(rnd):
    bank, acct, name, card = rnd.choice(_BANKS), gen_account(rnd), rnd.choice(_NAMES), gen_card(rnd)
    return (f"환불 계좌 {bank} {acct} (예금주 {name}), 자동결제 카드번호 {card} 해지 요청.",
            [("ACCOUNT", acct), ("PERSON", name), ("CARD", card)])


def s_quote_inline(rnd):
    name, rrn = rnd.choice(_NAMES), gen_rrn(rnd)
    return (f"제출 서류에 \"{name}({rrn})\"으로 기재되어 있어 정정이 필요합니다.",
            [("PERSON", name), ("RRN", rrn)])


def s_address_change(rnd):
    a1, a2, phone = rnd.choice(_ADDR_ROAD), rnd.choice(_ADDR_JIBUN), gen_phone(rnd)
    return (f"거주지를 {a1}에서 {a2}로 이전하였으며 변경 연락처는 {phone}입니다.",
            [("ADDRESS", a1), ("ADDRESS", a2), ("PHONE", phone)])


_STRATEGIES = [s_colon_form_spaced, s_complaint_sentence, s_footer_contact, s_list_items,
               s_corp_party, s_payment_line, s_quote_inline, s_address_change]


# ── base 문단 (aihub_71845, 사전 redaction) ──────────────────────
def load_base(rnd: random.Random, n: int) -> list[str]:
    paras = []
    for f in sorted((ROOT / "data/corpus/aihub_71845").glob("*.txt")):
        for block in f.read_text(encoding="utf-8").split("\n\n"):
            b = block.strip()
            if 150 <= len(b) <= 1500:
                paras.append(b)
    rnd.shuffle(paras)
    out = []
    for p in paras:
        if len(out) >= n:
            break
        out.append(_redact_existing_pii(p))
    return out


def build_doc(base: str, rnd: random.Random) -> dict:
    k = rnd.randint(2, 4)
    strategies = rnd.sample(_STRATEGIES, k)
    sentences = base.split(". ")
    positions = sorted(rnd.randint(0, len(sentences)) for _ in range(k))
    text, spans = "", []
    si = 0
    for idx in range(len(sentences) + 1):
        while si < k and positions[si] == idx:
            snippet, plist = strategies[si](rnd)
            if text and not text.endswith("\n"):
                text += "\n"
            snippet_start = len(text)
            text += snippet + "\n"
            for label, value in plist:
                rel = snippet.find(value)
                assert rel >= 0, (label, value)
                spans.append({"label": label, "start": snippet_start + rel,
                              "end": snippet_start + rel + len(value), "text": value})
            si += 1
        if idx < len(sentences):
            sep = ". " if idx and not text.endswith("\n") and text else ""
            if text and not text.endswith("\n") and sep == "":
                sep = ". "
            text += (sep if text and not text.endswith("\n") else "") + sentences[idx]
    for s in spans:  # gold 무결성
        assert text[s["start"]:s["end"]] == s["text"]
    return {"text": text, "spans": spans}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "data/corpus/external_inject_v2.jsonl"))
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    bases = load_base(rnd, args.n)
    assert len(bases) >= args.n, f"base 문단 부족: {len(bases)}"
    from collections import Counter
    dist = Counter()
    with open(args.out, "w", encoding="utf-8") as f:
        for b in bases[:args.n]:
            doc = build_doc(b, rnd)
            dist.update(s["label"] for s in doc["spans"])
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"저장: {args.out}  ({args.n} docs, {sum(dist.values())} spans)")
    for lab, c in dist.most_common():
        print(f"  {lab:14s} {c}")


if __name__ == "__main__":
    sys.exit(main() or 0)
