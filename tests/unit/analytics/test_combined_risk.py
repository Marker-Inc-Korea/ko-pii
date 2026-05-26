from ko_pii.analytics.combined_risk import (
    AttributeClass, classify_attribute, score_combined_risk,
)
from ko_pii.core.types import DetectionResult, RiskLevel


def _det(label):
    return DetectionResult(
        label=label, text="x", start=0, end=1,
        risk_level=RiskLevel.HIGH,
    )


class TestClassifyAttribute:
    def test_identifiers(self):
        for label in ("RRN", "FRN", "PASSPORT", "DRIVER_LICENSE", "CARD"):
            assert classify_attribute(label) == AttributeClass.IDENTIFIER

    def test_quasi_identifiers(self):
        for label in ("PERSON", "PHONE", "EMAIL", "ADDRESS", "VEHICLE"):
            assert classify_attribute(label) == AttributeClass.QUASI_IDENTIFIER

    def test_sensitive(self):
        assert classify_attribute("MEDICAL_INSURANCE") == AttributeClass.SENSITIVE

    def test_general(self):
        assert classify_attribute("URL") == AttributeClass.GENERAL
        assert classify_attribute("UNKNOWN") == AttributeClass.GENERAL


class TestCombinedRiskScoring:
    def test_identifier_present_critical(self):
        rpt = score_combined_risk([_det("RRN")])
        assert rpt.combined_risk == RiskLevel.CRITICAL
        assert "RRN" in rpt.distinct_identifiers

    def test_single_quasi_low(self):
        rpt = score_combined_risk([_det("PERSON")])
        assert rpt.combined_risk == RiskLevel.LOW

    def test_two_quasi_medium(self):
        rpt = score_combined_risk([_det("PERSON"), _det("PHONE")])
        assert rpt.combined_risk == RiskLevel.MEDIUM

    def test_four_quasi_high(self):
        rpt = score_combined_risk([
            _det("PERSON"), _det("PHONE"), _det("EMAIL"), _det("ADDRESS"),
        ])
        assert rpt.combined_risk == RiskLevel.HIGH
        assert len(rpt.distinct_quasi) == 4

    def test_sensitive_escalates(self):
        # 2 quasi + sensitive → MEDIUM → HIGH
        rpt = score_combined_risk([
            _det("PERSON"), _det("PHONE"), _det("MEDICAL_INSURANCE"),
        ])
        assert rpt.combined_risk == RiskLevel.HIGH

    def test_re_identifiable_flag(self):
        rpt = score_combined_risk([_det("RRN")])
        assert rpt.is_re_identifiable() is True
        rpt2 = score_combined_risk([_det("PERSON")])
        assert rpt2.is_re_identifiable() is False

    def test_no_detections_info(self):
        rpt = score_combined_risk([])
        assert rpt.combined_risk == RiskLevel.INFO

    def test_rationale_contains_explanation(self):
        rpt = score_combined_risk([_det("RRN"), _det("PERSON")])
        assert any("식별자" in r for r in rpt.rationale)

    def test_duplicate_labels_counted_once(self):
        rpt = score_combined_risk([_det("PERSON"), _det("PERSON")])
        assert len(rpt.distinct_quasi) == 1
        assert rpt.combined_risk == RiskLevel.LOW
