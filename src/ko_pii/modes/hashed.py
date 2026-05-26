"""Hashed mode — salt + SHA-256 일관성 식별자.

원본은 복원할 수 없지만, 같은 원본은 같은 해시 → 동일성 분석 가능.
Vault salt 를 공유하면 문서 간 일관성도 유지.

Legal basis: 개인정보보호법 비식별 조치 가이드라인 (해시 기반 가명처리).
"""
from __future__ import annotations

from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult
from ko_pii.modes._apply import apply_substitutions
from ko_pii.vault.reversible import ReversibleVault


def hashed(
    text: str,
    detections: Iterable[DetectionResult],
    vault: Optional[ReversibleVault] = None,
    digest_len: int = 12,
) -> tuple[str, ReversibleVault]:
    """Replace each detection with ``<LABEL:hash>`` derived from a salted SHA-256.

    ``digest_len`` truncates the hex digest for readability (default 12 chars
    ≈ 48 bits — collision-resistant within a typical document).
    """
    v = vault if vault is not None else ReversibleVault()
    detections = list(detections)

    def _replace(d: DetectionResult) -> str:
        fp = v.fingerprint(d.label, d.text)
        return f"<{d.label}:{fp[:digest_len]}>"

    replaced = apply_substitutions(text, detections, _replace)
    return replaced, v
