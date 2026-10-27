"""Hashed mode — Vault fingerprint 기반의 일관성 식별자.

복원용 Vault 항목을 만들지 않지만 메모리 지문 캐시에는 원문이 남을 수 있다.
저엔트로피 값은 비밀 키 없이 추측 공격이 가능하다.
같은 라벨·원문과 Vault 지문 설정(키·salt·scheme·반복 횟수)에서 같은 결과를 얻는다.
신규 Vault는 PBKDF2, 과거 Vault는 저장된 지문 scheme을 따른다.

Legal basis: 개인정보보호법 비식별 조치 가이드라인 (해시 기반 가명처리).
"""
from __future__ import annotations

from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult
from ko_pii.modes._apply import apply_substitutions, prepare_detections
from ko_pii.vault.reversible import ReversibleVault


def hashed(
    text: str,
    detections: Iterable[DetectionResult],
    vault: Optional[ReversibleVault] = None,
    digest_len: int = 12,
) -> tuple[str, ReversibleVault]:
    """Replace each detection with ``<LABEL:hash>`` from its Vault fingerprint.

    ``digest_len`` must be an integer from 1 to 64 (default 12 hex characters,
    48 bits). Shorter digests collide more often; none is a unique-ID guarantee.
    """
    if type(digest_len) is not int or not 1 <= digest_len <= 64:
        raise ValueError("digest_len must be an integer from 1 to 64")
    detections = prepare_detections(text, detections)
    v = vault if vault is not None else ReversibleVault()

    def _replace(d: DetectionResult) -> str:
        fp = v.fingerprint(d.label, d.text)
        return f"<{d.label}:{fp[:digest_len]}>"

    replaced = apply_substitutions(text, detections, _replace)
    return replaced, v
