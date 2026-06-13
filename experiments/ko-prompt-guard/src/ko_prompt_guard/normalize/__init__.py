"""De-obfuscation pipeline: 난독화된 한국어를 원형으로 펴는 결정론 전처리.

순서가 중요하다 (멱등·합성):
  1. invisible 제거             (제로폭/제어/방향)       [ko-pii 이식]
  2. 호환자모 → 음절 결합        ('ㅈㅜ'→'주')          [jamo]  ← NFKC 보다 먼저!
  3. NFKC 폴딩                  (전각/NFD; 호환자모 보존) [ko-pii 이식]
  4. 호몰로그 폴딩               (키릴/그리스, mixed만)   [homoglyph]
  5. 칸별 분리 축약              ('무 시 해'→'무시해')    [spacing]

★ jamo 결합을 NFKC 보다 먼저 두는 이유: NFKC 가 호환자모(ㅋ)를 조합자모(ᄏ)로
분해해 'ㅋㅋ'를 깨고 종성 결합을 망친다. 먼저 음절로 합치고, 남은 호환자모는
NFKC 에서 보존한다.

각 단계는 정책 토글로 켜고 끈다. 반환은 ``(normalized, changed)``.
"""
from __future__ import annotations

from ..policy import GuardPolicy
from .homoglyph import fold_homoglyphs
from .jamo import combine_jamo
from .spacing import collapse_separators
from .unicode_base import needs_normalization, nfkc_fold, strip_invisible

__all__ = ["normalize", "needs_normalization"]


def normalize(text: str, policy: GuardPolicy) -> tuple[str, bool]:
    """De-obfuscate ``text`` per policy. Returns ``(normalized, changed)``."""
    original = text
    if policy.strip_invisible:
        text = strip_invisible(text)
    if policy.combine_jamo:
        text = combine_jamo(text)
    if policy.fold_nfkc:
        text = nfkc_fold(text)
    if policy.fold_homoglyphs:
        text = fold_homoglyphs(text)
    if policy.collapse_repeats:
        text = collapse_separators(text)
    return text, (text != original)
