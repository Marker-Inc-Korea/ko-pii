"""외부 toxicity 벤치 검증 — self-play 가 아닌 실데이터로 FPR/recall 측정.

self-authored 코퍼스의 F1 1.0 은 자기참조 수치이므로, 제3자가 만든 외부 라벨
(smilegate unsmile)에서 결정론 TOXICITY detector 의 실제 일반화를 측정한다.
결과는 정직하게 README 에 기록한다 — 결정론 시드는 외부 recall 이 낮아(≈30%)
의미적 toxicity 는 Tier-2(분류기) 가 필요함을 보여준다.

데이터: smilegate-ai/korean_unsmile_dataset (CC-BY-SA, GitHub raw). 멀티라벨
(혐오 8종 + 악플/욕설 + clean). 자동 다운로드(미존재 시).

실행:
    PYTHONPATH=src:<ko-pii>/src:<ko-prompt-guard>/src python eval/external_toxicity.py
"""
from __future__ import annotations

import collections
import csv
import sys
import urllib.request
from pathlib import Path

from ko_output_guard import Guard, Verdict

_URL = ("https://raw.githubusercontent.com/smilegate-ai/"
        "korean_unsmile_dataset/main/unsmile_valid_v1.0.tsv")
_CACHE = Path("/data1/mk04/eval_external/unsmile_valid_v1.0.tsv")
_HATE_COLS = ["여성/가족", "남성", "성소수자", "인종/국적", "연령", "지역", "종교", "기타 혐오"]


def _load() -> list[dict[str, str]]:
    if not _CACHE.exists():
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_URL, _CACHE)  # noqa: S310 (고정 https 출처)
    with _CACHE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} = {a / b * 100:.1f}%" if b else "n/a"


def main() -> int:
    rows = _load()
    g = Guard()
    s: collections.Counter[str] = collections.Counter()
    for r in rows:
        caught = g.check(r["문장"]).verdict is not Verdict.SAFE
        clean = r.get("clean") == "1"
        if clean:
            s["clean"] += 1
            s["clean_caught"] += caught
        else:
            s["toxic"] += 1
            s["toxic_caught"] += caught
        if r.get("악플/욕설") == "1":
            s["abuse"] += 1
            s["abuse_caught"] += caught
        if any(r.get(c) == "1" for c in _HATE_COLS):
            s["hate"] += 1
            s["hate_caught"] += caught
    print(f"=== ko-output-guard TOXICITY × unsmile (외부, N={len(rows)}) ===")
    print(f"FPR (clean→caught, 낮을수록 좋음): {_pct(s['clean_caught'], s['clean'])}")
    print(f"Recall 악플/욕설 : {_pct(s['abuse_caught'], s['abuse'])}")
    print(f"Recall 혐오(8종)  : {_pct(s['hate_caught'], s['hate'])}")
    print(f"Recall 전체 toxic : {_pct(s['toxic_caught'], s['toxic'])}")
    print("\n주의: 결정론 시드의 외부 recall 이 낮은 것은 설계상 한계다 — 의미적/신조어"
          " toxicity 는 Tier-2(분류기)로 보강해야 한다. self-play F1 은 '회귀 스위트 통과'일 뿐.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
