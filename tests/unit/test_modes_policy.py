from ko_pii.core.modes import (
    Action,
    ProcessingMode,
    policy_for,
)
from ko_pii.core.types import RiskLevel


class TestPolicyDecisions:
    def test_paranoid_blocks_low(self):
        p = policy_for(ProcessingMode.PARANOID)
        assert p.decide(RiskLevel.LOW, 0.6) == Action.BLOCK
        assert p.decide(RiskLevel.LOW, 0.4) == Action.REVIEW

    def test_strict_blocks_medium_only(self):
        p = policy_for(ProcessingMode.STRICT)
        assert p.decide(RiskLevel.HIGH, 0.9) == Action.BLOCK
        assert p.decide(RiskLevel.LOW, 0.95) == Action.REVIEW
        assert p.decide(RiskLevel.LOW, 0.1) == Action.ALLOW

    def test_balanced_high(self):
        p = policy_for(ProcessingMode.BALANCED)
        assert p.decide(RiskLevel.HIGH, 0.9) == Action.BLOCK
        assert p.decide(RiskLevel.MEDIUM, 0.9) == Action.REVIEW

    def test_permissive_critical_with_full_confidence(self):
        p = policy_for(ProcessingMode.PERMISSIVE)
        assert p.decide(RiskLevel.CRITICAL, 1.0) == Action.BLOCK
        # RRN with post-2020 (confidence 0.7) — review only under permissive
        assert p.decide(RiskLevel.CRITICAL, 0.7) == Action.REVIEW

    def test_audit_never_blocks(self):
        p = policy_for(ProcessingMode.AUDIT)
        assert p.decide(RiskLevel.CRITICAL, 1.0) == Action.ALLOW
