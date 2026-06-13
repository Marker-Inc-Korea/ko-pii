"""GuardPolicy: configures de-obfuscation and which signals block vs. flag.

Philosophy mirrors ko-pii / ko-sqlguard: the deterministic core is strong and
pure; ML/LLM review is a separate, opt-in Tier-2 seam (see semantic.py). Because
false positives here BLOCK real users, defaults are conservative.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .result import Category, Severity


class GuardPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- de-obfuscation pipeline toggles (Tier-1, pure) ---
    strip_invisible: bool = True       # zero-width / control / direction chars
    fold_nfkc: bool = True             # fullwidth / compatibility / NFD recombine
    combine_jamo: bool = True          # 'ㅈㅜ' -> '주' (conservative; protects ㅋㅋ/ㅠㅠ)
    fold_homoglyphs: bool = True       # Cyrillic/Greek look-alikes (mixed-script only)
    collapse_repeats: bool = True      # 'ㅁㅜㅜㅜㅅㅣ' / spaced-out tokens

    # --- detection toggles ---
    detect_encoding: bool = True       # base64 / hex / %xx payload heuristics
    de_leet: bool = True               # leetspeak digit->letter decode (보강 scan; '1gn0r3')

    # Treating obfuscation itself as a signal: if de-obfuscation changed the text
    # AND a pattern then matched, escalate. Pure obfuscation with no payload only
    # FLAGs (could be legitimate unicode).
    flag_pure_obfuscation: bool = False

    # Categories that BLOCK (vs. only FLAG) when matched at/above min severity.
    block_categories: frozenset[Category] = frozenset(
        {
            Category.INSTRUCTION_OVERRIDE,
            Category.PROMPT_LEAK,
            Category.JAILBREAK,
            Category.EXFILTRATION,
        }
    )
    min_block_severity: Severity = Severity.HIGH

    # --- Tier-2 seam: accepted but not enforced in v1 ---
    # A semantic/LLM reviewer threshold; the pure check() never reads this.
    embedding_threshold: float | None = None
