"""통합 Anonymizer — 검출 + 정책 결정 + 처리 (BLOCK / REVIEW / ALLOW) 의 외부 API.

    from ko_pii import Anonymizer, ProcessingMode

    anon = Anonymizer(mode=ProcessingMode.STRICT)
    result = anon.process("신청인 880101-1234568 연락처 010-1234-5678")
    print(result.text)        # 치환된 본문
    print(result.detections)  # 모든 검출 결과 (Action 포함)
    print(result.summary)     # by_risk / by_action / by_legal_basis
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ko_pii.analytics.combined_risk import (
    CombinedRiskReport,
    score_combined_risk,
)
from ko_pii.core.modes import Action, ProcessingMode, policy_for
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.detect import detect_all
from ko_pii.modes._apply import apply_substitutions
from ko_pii.modes.redact import label_to_hangul
from ko_pii.vault.reversible import ReversibleVault


@dataclass
class DetectionRecord:
    detection: DetectionResult
    action: Action
    token: Optional[str] = None


@dataclass
class AnonymizationResult:
    text: str
    detections: list[DetectionRecord]
    vault: Optional[ReversibleVault]
    summary: dict[str, Any] = field(default_factory=dict)
    combined_risk: Optional[CombinedRiskReport] = None

    def review_items(self) -> list[DetectionRecord]:
        return [r for r in self.detections if r.action == Action.REVIEW]

    def blocked_items(self) -> list[DetectionRecord]:
        return [r for r in self.detections if r.action == Action.BLOCK]


class Anonymizer:
    """High-level orchestration object.

    Parameters
    ----------
    mode :
        Threshold profile. See :class:`ko_pii.core.modes.ProcessingMode`.
    strategy :
        ``"tokenize"`` (reversible, default), ``"redact"`` (irreversible
        label), ``"asterisk"``, ``"hashed"``.
    vault :
        Optional pre-existing :class:`ReversibleVault`. A new one is created
        if absent (used for ``tokenize`` and ``hashed``).
    include / exclude :
        Filter detectors by label.
    """

    def __init__(
        self,
        mode: ProcessingMode = ProcessingMode.STRICT,
        strategy: str = "tokenize",
        vault: Optional[ReversibleVault] = None,
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
        secondary_detector: Any = None,
        merge_mode: str = "union",
        role_split_labels: Optional[Iterable[str]] = None,
    ) -> None:
        if strategy not in {"tokenize", "redact", "asterisk", "hashed",
                            "partial", "fpe"}:
            raise ValueError(f"Unknown strategy: {strategy}")
        self.mode = mode
        self.policy = policy_for(mode)
        self.strategy = strategy
        self.vault = vault if vault is not None else ReversibleVault()
        self.include = list(include) if include else None
        self.exclude = list(exclude) if exclude else None
        self.secondary_detector = secondary_detector
        self.merge_mode = merge_mode
        # role_split 모드에서 secondary 가 담당할 라벨 (None=기본 퍼지 10종)
        self.role_split_labels = (frozenset(role_split_labels)
                                  if role_split_labels is not None else None)

    # ------------------------------------------------------------ public

    def process(self, text: str) -> AnonymizationResult:
        primary = detect_all(
            text, include=self.include, exclude=self.exclude
        )
        # Optional secondary detector (ML 어댑터 등) 가 있으면 결과 병합
        if self.secondary_detector is not None:
            from ko_pii.integrations.hybrid import MergeMode, merge_detections
            secondary = list(self.secondary_detector.detect(text))
            if self.include:
                secondary = [s for s in secondary if s.label in self.include]
            if self.exclude:
                secondary = [s for s in secondary if s.label not in self.exclude]
            detections = merge_detections(
                primary, secondary, mode=MergeMode(self.merge_mode),
                role_split_labels=self.role_split_labels,
            )
        else:
            detections = primary
        decisions = [
            DetectionRecord(
                detection=d,
                action=self.policy.decide(d.risk_level, d.confidence),
            )
            for d in detections
        ]

        to_block = [r for r in decisions if r.action == Action.BLOCK]
        replaced = self._apply(text, to_block)
        combined = score_combined_risk(detections)
        summary = self._build_summary(decisions, combined)
        return AnonymizationResult(
            text=replaced,
            detections=decisions,
            vault=self.vault if self.strategy in {"tokenize", "hashed", "fpe"} else None,
            summary=summary,
            combined_risk=combined,
        )

    # ----------------------------------------------------------- internal

    def _apply(self, text: str, to_block: list[DetectionRecord]) -> str:
        if not to_block:
            return text

        if self.strategy == "tokenize":
            def repl(d: DetectionResult) -> str:
                tok = self.vault.store(
                    label=d.label,
                    original=d.text,
                    risk_level=int(d.risk_level),
                    legal_basis=d.legal_basis,
                    offset=d.start,
                    extra=dict(d.extra),
                )
                # Tag the record with the token assigned.
                for rec in to_block:
                    if rec.detection is d:
                        rec.token = tok
                        break
                return tok
            return apply_substitutions(
                text, (r.detection for r in to_block), repl
            )

        if self.strategy == "redact":
            def repl(d: DetectionResult) -> str:
                return f"[{label_to_hangul(d.label)}]"
            return apply_substitutions(
                text, (r.detection for r in to_block), repl
            )

        if self.strategy == "asterisk":
            def repl(d: DetectionResult) -> str:
                return "*" * max(1, d.end - d.start)
            return apply_substitutions(
                text, (r.detection for r in to_block), repl
            )

        if self.strategy == "hashed":
            def repl(d: DetectionResult) -> str:
                fp = self.vault.fingerprint(d.label, d.text)
                tok = f"<{d.label}:{fp[:12]}>"
                for rec in to_block:
                    if rec.detection is d:
                        rec.token = tok
                        break
                return tok
            return apply_substitutions(text, (r.detection for r in to_block), repl)

        if self.strategy == "partial":
            from ko_pii.modes.partial import mask_value
            def repl(d: DetectionResult) -> str:
                masked = mask_value(d.label, d.text)
                for rec in to_block:
                    if rec.detection is d:
                        rec.token = masked
                        break
                return masked
            return apply_substitutions(text, (r.detection for r in to_block), repl)

        # fpe
        from ko_pii.modes.fpe import _FPE_BY_LABEL, _fpe_default
        def repl_fpe(d: DetectionResult) -> str:
            fp = self.vault.fingerprint(d.label, d.text)
            fn = _FPE_BY_LABEL.get(d.label, _fpe_default)
            new_val = fn(d.text, fp)
            self.vault.store(
                label=d.label,
                original=d.text,
                risk_level=int(d.risk_level),
                legal_basis=d.legal_basis,
                offset=d.start,
                extra={**dict(d.extra), "fpe_value": new_val},
            )
            for rec in to_block:
                if rec.detection is d:
                    rec.token = new_val
                    break
            return new_val
        return apply_substitutions(text, (r.detection for r in to_block), repl_fpe)

    def _build_summary(
        self,
        decisions: list[DetectionRecord],
        combined: CombinedRiskReport,
    ) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        by_label: dict[str, int] = {}
        by_legal: dict[str, int] = {}
        for r in decisions:
            by_action[r.action.value] = by_action.get(r.action.value, 0) + 1
            risk_name = RiskLevel(r.detection.risk_level).name
            by_risk[risk_name] = by_risk.get(risk_name, 0) + 1
            by_label[r.detection.label] = by_label.get(r.detection.label, 0) + 1
            lb = r.detection.legal_basis or "—"
            by_legal[lb] = by_legal.get(lb, 0) + 1
        return {
            "combined_risk": combined.combined_risk.name,
            "combined_rationale": list(combined.rationale),
            "distinct_identifiers": list(combined.distinct_identifiers),
            "distinct_quasi_identifiers": list(combined.distinct_quasi),
            "sensitive_attributes": list(combined.sensitive_present),
            "total": len(decisions),
            "mode": self.mode.value,
            "strategy": self.strategy,
            "by_action": by_action,
            "by_risk": by_risk,
            "by_label": by_label,
            "by_legal_basis": by_legal,
        }
