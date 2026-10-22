from dataclasses import replace
import itertools

import pytest

from ko_pii import Anonymizer, CallableDetector, DetectionResult, RegexDetector, RiskLevel


def test_named_capture_preserves_context_and_uses_existing_label():
    detector = RegexDetector(r"사번: (?P<value>EMP-\d{4})", label="ACCOUNT", group="value")
    result = Anonymizer(strategy="redact", include=["ACCOUNT"], secondary_detector=detector).process("사번: EMP-1042")
    assert result.text == "사번: [계좌번호]"
    d = result.detections[0].detection
    assert (d.text, d.start, d.end) == ("EMP-1042", 4, 12)


@pytest.mark.parametrize("kw", [
    {"pattern": "["}, {"pattern": b"x"}, {"pattern": ""}, {"label": "NEW_LABEL"},
    {"label": []}, {"group": 2}, {"group": True}, {"group": "missing"},
    {"confidence": float("nan")}, {"confidence": float("inf")}, {"confidence": True},
    {"confidence": -0.1}, {"confidence": 1.1}, {"risk_level": 4},
    {"confidence": 10 ** 400},
    {"max_chars": 0}, {"max_matches": -1}, {"max_matches": True},
])
def test_regex_bad_configuration(kw):
    with pytest.raises(ValueError):
        RegexDetector(**{"pattern": "x", "label": "PERSON", **kw})


BASE = DetectionResult("PERSON", "abc", 0, 3, RiskLevel.HIGH)


@pytest.mark.parametrize("bad", [
    None, "abc", replace(BASE, start=True), replace(BASE, start=-1), replace(BASE, end=4),
    replace(BASE, end=0), replace(BASE, start=1), replace(BASE, text="secret"),
    replace(BASE, label="SECRET"), replace(BASE, risk_level="HIGH"),
    replace(BASE, confidence=float("nan")), replace(BASE, confidence=2),
])
def test_callable_invalid_second_result_never_yields_partial_or_modifies_vault(bad):
    detector = CallableDetector(lambda text: [BASE, bad])
    it = detector.detect("abc")
    with pytest.raises(ValueError):
        next(it)
    anon = Anonymizer(secondary_detector=detector)
    with pytest.raises(ValueError):
        anon.process("abc")
    assert len(anon.vault) == 0


def test_callback_exception_is_not_a_raw_source_disclosure():
    def broken(text):
        raise RuntimeError(text)
    with pytest.raises(ValueError) as error:
        list(CallableDetector(broken).detect("DO_NOT_LOG_THIS"))
    assert "DO_NOT_LOG_THIS" not in str(error.value)


def test_limits_empty_optional_groups_and_metadata():
    with pytest.raises(ValueError):
        list(CallableDetector(lambda text: itertools.repeat(BASE), max_matches=2).detect("abc"))
    with pytest.raises(ValueError):
        list(RegexDetector("x", label="PERSON", max_chars=2).detect("xxx"))
    with pytest.raises(ValueError):
        list(RegexDetector("x*", label="PERSON").detect("abc"))
    assert list(RegexDetector("(abc)?x", label="PERSON", group=1).detect("x")) == []
    value = replace(BASE, evidence=["secret"], extra={"secret": "secret"}, legal_basis="secret", rule_id="secret")
    result = list(CallableDetector(lambda text: [value]).detect("abc"))[0]
    assert result == BASE
    assert result is not value


def test_custom_results_still_obey_include_and_exclude():
    detector = RegexDetector("abc", label="PERSON")
    with pytest.raises(ValueError):
        Anonymizer(include=[], secondary_detector=detector)
    assert Anonymizer(include=["EMAIL"], secondary_detector=detector).process("abc").text == "abc"
    assert Anonymizer(exclude=["PERSON"], secondary_detector=detector).process("abc").text == "abc"
