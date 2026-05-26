"""Reversible tokenization mode.

각 검출 결과를 ``<LABEL_N>`` 토큰으로 치환하고, Vault 에 원본을 저장한다.
같은 원본 값은 같은 토큰을 받는다 (문서 내 일관성). Vault 가 있으면 원본 복원 가능.

Legal basis: 개인정보보호법 제28조의2~5 (가명정보 처리 특례).
"""
from __future__ import annotations

from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult
from ko_pii.modes._apply import apply_substitutions
from ko_pii.vault.reversible import ReversibleVault


def tokenize(
    text: str,
    detections: Iterable[DetectionResult],
    vault: Optional[ReversibleVault] = None,
) -> tuple[str, ReversibleVault]:
    """Replace each detection span with a stable ``<LABEL_N>`` token.

    Returns ``(replaced_text, vault)``. If no vault is supplied a fresh one is
    created. The same vault can be reused across multiple calls to maintain
    token identity across documents.
    """
    v = vault if vault is not None else ReversibleVault()
    detections = list(detections)  # consume iterator once

    def _replace(d: DetectionResult) -> str:
        return v.store(
            label=d.label,
            original=d.text,
            risk_level=int(d.risk_level),
            legal_basis=d.legal_basis,
            offset=d.start,
            extra=dict(d.extra),
        )

    replaced = apply_substitutions(text, detections, _replace)
    return replaced, v
