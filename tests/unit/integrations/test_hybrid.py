from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.integrations import MergeMode, merge_detections


def _det(label, start, end, text, risk=RiskLevel.MEDIUM, conf=0.8, evidence=None):
    return DetectionResult(
        label=label, text=text, start=start, end=end,
        risk_level=risk, confidence=conf,
        evidence=evidence or [],
    )


class TestMergeUnion:
    def test_non_overlapping_union(self):
        primary = [_det("PERSON", 0, 3, "홍길동")]
        secondary = [_det("EMAIL", 10, 20, "a@b.com")]
        out = merge_detections(primary, secondary, mode=MergeMode.UNION)
        assert len(out) == 2
        labels = {r.label for r in out}
        assert labels == {"PERSON", "EMAIL"}

    def test_overlapping_higher_risk_wins(self):
        primary = [_det("PERSON", 0, 3, "홍길동", risk=RiskLevel.HIGH)]
        secondary = [_det("PERSON", 0, 3, "홍길동", risk=RiskLevel.MEDIUM)]
        out = merge_detections(primary, secondary, mode=MergeMode.UNION)
        assert len(out) == 1
        assert out[0].risk_level == RiskLevel.HIGH


class TestMergeIntersection:
    def test_only_both_detect(self):
        primary = [
            _det("PERSON", 0, 3, "홍길동"),
            _det("EMAIL", 10, 20, "x@y.z"),  # secondary 안 잡음
        ]
        secondary = [
            _det("PERSON", 0, 3, "홍길동"),
            _det("PHONE", 30, 40, "010-1234"),  # primary 안 잡음
        ]
        out = merge_detections(primary, secondary, mode=MergeMode.INTERSECTION)
        # PERSON 만 양쪽 모두 잡음 → 1건
        assert len(out) == 1
        assert out[0].label == "PERSON"
        # corroboration 증거 부착
        assert any("corroborated_by" in e for e in out[0].evidence)


class TestMergeEnrich:
    def test_primary_wins_secondary_adds_new(self):
        primary = [_det("PERSON", 0, 3, "홍길동", risk=RiskLevel.HIGH)]
        secondary = [
            _det("PERSON", 0, 3, "홍길동", risk=RiskLevel.MEDIUM),
            _det("EMAIL", 20, 30, "a@b.c"),  # primary 가 놓침
        ]
        out = merge_detections(primary, secondary, mode=MergeMode.ENRICH_PRIMARY)
        assert len(out) == 2
        # primary 결과는 enriched
        person = next(r for r in out if r.label == "PERSON")
        assert "corroborated_by:secondary(PERSON)" in person.evidence
        # secondary 만 잡은 것은 *추가됨*
        emails = [r for r in out if r.label == "EMAIL"]
        assert len(emails) == 1


class TestMergeCrossValidation:
    def test_corroborated_full_confidence(self):
        primary = [_det("PERSON", 0, 3, "홍길동", conf=0.7)]
        secondary = [_det("PERSON", 0, 3, "홍길동", conf=0.9)]
        out = merge_detections(primary, secondary, mode=MergeMode.CROSS_VALIDATION)
        assert len(out) == 1
        assert out[0].confidence >= 0.7
        assert any("corroborated_by" in e for e in out[0].evidence)

    def test_uncorroborated_penalty(self):
        primary = []
        secondary = [_det("PERSON", 0, 3, "이상함", conf=0.9)]
        out = merge_detections(primary, secondary, mode=MergeMode.CROSS_VALIDATION)
        assert len(out) == 1
        # primary 가 안 잡음 → 페널티 0.9*0.7 = 0.63
        assert out[0].confidence < 0.7
        assert any("uncorroborated" in e for e in out[0].evidence)


class TestMergeFallback:
    def test_returns_primary_only(self):
        primary = [_det("PERSON", 0, 3, "홍길동")]
        secondary = [_det("PHONE", 10, 20, "010-1234")]
        out = merge_detections(primary, secondary, mode=MergeMode.FALLBACK_SECONDARY)
        # FALLBACK 모드는 primary 만 반환 (secondary 는 호출자가 별도 처리)
        assert len(out) == 1
        assert out[0].label == "PERSON"


class TestOverlapLeakRegression:
    """늦게 시작하는 고위험 PII 가 먼저 시작한 저위험 span 에 가려 누출되던 회귀 차단.

    과거 hybrid._resolve_overlaps 가 start-우선 단일커서라, ADDRESS(LOW)[0,20) 가
    RRN(CRITICAL)[10,23) 보다 먼저 시작한다는 이유로 RRN 을 드롭 → 주민번호 평문 누출.
    정본(core.overlap, 위험도 우선)으로 통일해 RRN 이 살아남아야 한다.
    """

    def test_later_starting_critical_survives_merge(self):
        addr = _det("ADDRESS", 0, 20, "서울시 강남구 어딘가",
                    risk=RiskLevel.LOW, conf=0.6)
        rrn = _det("RRN", 10, 23, "880101-1234567",
                   risk=RiskLevel.CRITICAL, conf=1.0)
        out = merge_detections([addr], [rrn], mode=MergeMode.UNION)
        labels = {r.label for r in out}
        assert "RRN" in labels, "고위험 RRN 이 병합에서 드롭되면 평문 누출"
        assert "ADDRESS" not in labels  # 저위험 span 은 고위험에 밀려 제거
