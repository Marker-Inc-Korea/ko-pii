"""평가: 한국어 난독 정규화의 인과 효과(ΔRecall) + 탐지 F1 + 오탐 FPR.

    PYTHONPATH=src python eval/measure.py

핵심 주장: 정규화를 끄면(=영어 가드처럼 난독을 못 펴면) 난독 인젝션을 거의 못 잡고,
켜면 잡는다 — 그러면서 정상문은 안 깬다(ΔFPR≈0). ko-pii 의 hard-negative ablation
정직성 규약을 그대로 따른다(단일 변수 격리).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import NORMAL, SEMANTIC_INJECTIONS, obfuscated_pairs  # noqa: E402

from ko_prompt_guard import Guard, GuardPolicy, Verdict  # noqa: E402

_ON = Guard(GuardPolicy())
_OFF = Guard(GuardPolicy(
    strip_invisible=False, fold_nfkc=False, combine_jamo=False,
    fold_homoglyphs=False, collapse_repeats=False,
))


def _detected(guard: Guard, text: str) -> bool:
    return guard.check(text).verdict is not Verdict.ALLOW


def main() -> None:
    pairs = obfuscated_pairs()

    # 1) ΔRecall — 난독 변종에서 정규화 ON vs OFF (단일 변수: 정규화).
    by_fam: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # [n, on, off]
    for fam, _base, obf in pairs:
        by_fam[fam][0] += 1
        by_fam[fam][1] += _detected(_ON, obf)
        by_fam[fam][2] += _detected(_OFF, obf)
    n = len(pairs)
    on = sum(_detected(_ON, o) for _, _, o in pairs)
    off = sum(_detected(_OFF, o) for _, _, o in pairs)

    print("=" * 64)
    print(f"난독 인젝션 변종 {n}개 — 정규화 인과 효과 (ΔRecall)")
    print(f"  정규화 OFF Recall: {off}/{n} = {off / n:.0%}")
    print(f"  정규화 ON  Recall: {on}/{n} = {on / n:.0%}")
    print(f"  ★ ΔRecall = +{(on - off) / n:.0%}")
    print("  난독 종류별 (ON / OFF):")
    for fam, (fn_, fon, foff) in sorted(by_fam.items()):
        print(f"    {fam:10s} {fon}/{fn_} ({fon / fn_:.0%})  vs  OFF {foff}/{fn_} ({foff / fn_:.0%})")

    # 2) 탐지 F1 + FPR — 공격(난독변종+의미) vs 정상.
    attacks = [o for _, _, o in pairs] + SEMANTIC_INJECTIONS
    tp = sum(_detected(_ON, a) for a in attacks)
    fn = len(attacks) - tp
    fp = sum(_detected(_ON, x) for x in NORMAL)
    tn = len(NORMAL) - fp
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print("=" * 64)
    print(f"탐지 성능 (정규화 ON) — 공격 {len(attacks)} / 정상 {len(NORMAL)}")
    print(f"  Precision {prec:.3f}  Recall {rec:.3f}  F1 {f1:.3f}")
    print(f"  FPR(정상 오탐) {fp}/{len(NORMAL)} = {fpr:.0%}")
    if fp:
        print("  과탐 사례:", [x for x in NORMAL if _detected(_ON, x)])
    miss = [a for a in attacks if not _detected(_ON, a)]
    if miss:
        print("  놓친 공격:", miss)
    print("=" * 64)


if __name__ == "__main__":
    main()
