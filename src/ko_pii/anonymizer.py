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
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Iterable, Optional

from ko_pii.analytics.combined_risk import (
    CombinedRiskReport,
    score_combined_risk,
)
from ko_pii.core.modes import Action, ProcessingMode, policy_for
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.detect import detect_all
from ko_pii.labels import validate_label_filter
from ko_pii.modes._apply import AppliedSpan, apply_substitutions
from ko_pii.modes.redact import label_to_hangul
from ko_pii.patterns.person import is_person_excluded, normalize_exclusions
from ko_pii.policy import policy_digest, validate_strategies
from ko_pii.vault.reversible import ReversibleVault


@dataclass
class DetectionRecord:
    detection: DetectionResult
    action: Action
    token: Optional[str] = None
    strategy: Optional[str] = None


@dataclass
class AnonymizationResult:
    text: str
    detections: list[DetectionRecord]
    vault: Optional[ReversibleVault]
    summary: dict[str, Any] = field(default_factory=dict)
    combined_risk: Optional[CombinedRiskReport] = None
    substitutions: list[AppliedSpan] = field(default_factory=list)

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
    person_exclusions :
        Domain terms to suppress only from PERSON detection for this instance.
    strategies :
        Optional per-label overrides for ``strategy``. Detection thresholds still
        follow ``mode``; overrides do not turn REVIEW/ALLOW into BLOCK.
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
        person_exclusions: Optional[Iterable[str]] = None,
        *,
        strategies: Mapping[str, str] | None = None,
    ) -> None:
        self.strategies = MappingProxyType(validate_strategies(strategy, strategies))
        self.mode = mode
        self.policy = policy_for(mode)
        self.strategy = strategy
        self.vault = vault if vault is not None else ReversibleVault()
        self.include = validate_label_filter(include, name="include")
        self.exclude = validate_label_filter(exclude, name="exclude")
        self.secondary_detector = secondary_detector
        self.merge_mode = merge_mode
        # role_split 모드에서 secondary 가 담당할 라벨 (None=기본 퍼지 10종)
        self.role_split_labels = (frozenset(role_split_labels)
                                  if role_split_labels is not None else None)
        self.person_exclusions = normalize_exclusions(person_exclusions)

    # ------------------------------------------------------------ public

    def process(self, text: str) -> AnonymizationResult:
        primary = detect_all(
            text,
            include=self.include,
            exclude=self.exclude,
            person_exclusions=self.person_exclusions,
        )
        # Optional secondary detector (ML 어댑터 등) 가 있으면 결과 병합
        if self.secondary_detector is not None:
            from ko_pii.integrations.hybrid import MergeMode, merge_detections
            secondary = list(self.secondary_detector.detect(text))
            if self.include:
                secondary = [s for s in secondary if s.label in self.include]
            if self.exclude:
                secondary = [s for s in secondary if s.label not in self.exclude]
            if self.person_exclusions:
                # Filter before overlap resolution. An excluded PERSON must not
                # displace an overlapping primary ADDRESS or identifier.
                secondary = [
                    detection
                    for detection in secondary
                    if not (
                        detection.label == "PERSON"
                        and is_person_excluded(
                            detection.text,
                            self.person_exclusions,
                        )
                    )
                ]
            detections = merge_detections(
                primary, secondary, mode=MergeMode(self.merge_mode),
                role_split_labels=self.role_split_labels,
            )
        else:
            detections = primary
        return self._process_detections(text, detections)

    def strategy_for(self, label: str) -> str:
        """Return the configured transformation, without changing mode thresholds."""
        return self.strategies.get(label, self.strategy)

    def _process_detections(
        self, text: str, detections: list[DetectionResult], *, asserted: bool = False,
    ) -> AnonymizationResult:
        decisions = [
            DetectionRecord(
                detection=d,
                action=(Action.BLOCK if asserted and self.mode != ProcessingMode.AUDIT
                        else self.policy.decide(d.risk_level, d.confidence)),
                strategy=self.strategy_for(d.label),
            )
            for d in detections
        ]

        to_block = [r for r in decisions if r.action == Action.BLOCK]
        substitutions: list[AppliedSpan] = []
        replaced = self._apply(text, to_block, substitutions)
        combined = score_combined_risk(detections)
        summary = self._build_summary(decisions, combined)
        summary["detection_scope"] = {
            "input_empty": not text, "asserted_field": asserted,
            "include": sorted(self.include) if self.include is not None else None,
            "exclude": sorted(self.exclude) if self.exclude is not None else [],
            "combined_risk_basis": "observed_labels_heuristic_not_anonymity_assessment",
        }
        return AnonymizationResult(
            text=replaced,
            detections=decisions,
            vault=self.vault if ({self.strategy, *self.strategies.values()}
                                 & {"tokenize", "hashed", "fpe"}) else None,
            summary=summary,
            combined_risk=combined,
            substitutions=substitutions,
        )

    # ----------------------------------------------------------- internal

    def _apply(
        self, text: str, to_block: list[DetectionRecord], trace: list[AppliedSpan],
    ) -> str:
        if not to_block:
            return text

        records_by_detection = {id(rec.detection): rec for rec in reversed(to_block)}

        def repl(d: DetectionResult) -> str:
            record = records_by_detection[id(d)]
            strategy = self.strategy_for(d.label)
            if strategy == "tokenize":
                tok = self.vault.store(
                    label=d.label,
                    original=d.text,
                    risk_level=int(d.risk_level),
                    legal_basis=d.legal_basis,
                    offset=d.start,
                    extra=dict(d.extra),
                )
                # Tag the record with the token assigned.
                record.token = tok
                return tok
            if strategy == "redact":
                return f"[{label_to_hangul(d.label)}]"
            if strategy == "asterisk":
                return "*" * max(1, d.end - d.start)
            if strategy == "hashed":
                fp = self.vault.fingerprint(d.label, d.text)
                tok = f"<{d.label}:{fp[:12]}>"
                record.token = tok
                return tok
            if strategy == "partial":
                from ko_pii.modes.partial import mask_value
                masked = mask_value(d.label, d.text)
                record.token = masked
                return masked
            from ko_pii.modes.fpe import _pseudonymize_value
            fp = self.vault.fingerprint(d.label, d.text)
            new_val = _pseudonymize_value(d.label, d.text, fp)
            self.vault.store(
                label=d.label,
                original=d.text,
                risk_level=int(d.risk_level),
                legal_basis=d.legal_basis,
                offset=d.start,
                extra={**dict(d.extra), "fpe_value": new_val},
            )
            record.token = new_val
            return new_val
        return apply_substitutions(text, (r.detection for r in to_block), repl, trace=trace)

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
            "strategies": dict(self.strategies),
            "transformation_policy_sha256": policy_digest(self.mode.value, self.strategy, self.strategies),
            "by_action": by_action,
            "by_risk": by_risk,
            "by_label": by_label,
            "by_legal_basis": by_legal,
        }
