import json

import pytest

from ko_pii import Anonymizer, DetectionResult, RegexDetector, RiskLevel, anonymize_json
from ko_pii.cli import main
from ko_pii.core.overlap import resolve_overlaps
from ko_pii.core.trace import OverlapTrace
from ko_pii.integrations.hybrid import MergeMode, merge_detections
from ko_pii.reporting import explain
from ko_pii.core.modes import ProcessingMode


@pytest.mark.parametrize("text,subrule", [
    ("user@example.com", "email.ascii.v1"), ("user@예시.kr", "email.korean_domain.v1"),
    ("user [at] example [dot] com", "email.obfuscated.v1"),
    ("ｕｓｅｒ@example.com", "email.ascii.v1"),
])
def test_stable_email_subrules_and_no_values(text, subrule):
    result = Anonymizer(include=["EMAIL"], trace_limit=5).process(text)
    report = explain(result)
    assert report["findings"][0]["rule_id"] == "ko-pii.email.v1"
    assert report["findings"][0]["subrule_id"] == subrule
    assert "overlap_trace" not in report
    assert text not in json.dumps(explain(result, include_trace=True), ensure_ascii=False)


def _d(start=0, end=3, risk=RiskLevel.HIGH, confidence=1.0):
    return DetectionResult("PERSON", "NEVER_EXPORT_THIS", start, end, risk, confidence,
                           evidence=["NEVER_EXPORT_THIS"], extra={"value": "NEVER_EXPORT_THIS"},
                           rule_id="NEVER_EXPORT_THIS", subrule_id="NEVER_EXPORT_THIS")


@pytest.mark.parametrize("loser,winner,reason", [
    (_d(risk=RiskLevel.LOW), _d(), "lower_risk_priority"),
    (_d(confidence=0.5), _d(), "lower_confidence_priority"),
    (_d(end=2), _d(), "shorter_span_priority"),
    (_d(start=1, end=4), _d(), "later_start_priority"),
    (_d(), _d(), "stable_input_order_tie"),
])
def test_priority_reason_and_one_real_blocker(loser, winner, reason):
    trace = OverlapTrace(5)
    assert resolve_overlaps([winner, loser], trace=trace) == [winner]
    report = trace.report()
    assert report["stages"]["primary"] == {"candidates": 2, "kept": 1, "discarded": 1}
    assert report["discarded"][0]["reason"] == reason
    assert report["discarded"][0]["blocker"]["source_span"] == [winner.start, winner.end]
    assert "NEVER_EXPORT_THIS" not in json.dumps(report)
    report["discarded"][0]["candidate"]["source_span"][0] = 12345
    assert trace.report()["discarded"][0]["candidate"]["source_span"][0] == loser.start


def test_bounded_trace_and_decisions_are_unchanged():
    items = [_d()] * 100
    trace = OverlapTrace(2)
    assert resolve_overlaps(items, trace=trace) == resolve_overlaps(items)
    assert trace.report()["omitted_events"] == 97
    assert trace.report()["truncated"] is True
    assert len(trace.report()["discarded"]) == 2


@pytest.mark.parametrize("mode", list(MergeMode))
def test_hybrid_trace_does_not_change_merge_results(mode):
    primary, secondary = [_d()], [_d(end=2)]
    trace = OverlapTrace()
    assert merge_detections(primary, secondary, mode, trace=trace) == merge_detections(primary, secondary, mode)
    assert "hybrid" in trace.report()["stages"]


@pytest.mark.parametrize("mode", list(MergeMode))
def test_supported_subrule_survives_hybrid_enrichment(mode):
    primary = Anonymizer(include=["EMAIL"]).process("user@example.com").detections[0].detection
    secondary = DetectionResult("EMAIL", primary.text, primary.start, primary.end, RiskLevel.LOW)
    result = merge_detections([primary], [secondary], mode)
    assert result[0].rule_id == "ko-pii.email.v1"
    assert result[0].subrule_id == "email.ascii.v1"


def test_trace_is_per_call_opt_in_and_records_secondary_overlap():
    anon = Anonymizer(trace_limit=3, include=["EMAIL"],
                      secondary_detector=RegexDetector(r"user@example\.com", label="EMAIL", risk_level=RiskLevel.LOW))
    first = anon.process("user@example.com")
    report = explain(first, include_trace=True)
    assert report["overlap_trace"]["stages"]["hybrid"]["discarded"] == 1
    second = anon.process("plain")
    assert second.overlap_trace is not first.overlap_trace
    assert second.overlap_trace.report()["discarded"] == []
    assert Anonymizer().process("user@example.com").overlap_trace is None
    assert explain(Anonymizer().process("plain"), include_trace=True)["overlap_trace"] is None
    asserted = anonymize_json({"name": "홍길동"}, anonymizer=anon, field_labels={"/name": "EMAIL"})
    assert asserted.report(include_trace=True)["fields"][0]["overlap_trace"] is None


@pytest.mark.parametrize("limit", [-1, 1001, True, 1.1, "5"])
def test_trace_bounds(limit):
    with pytest.raises(ValueError):
        Anonymizer(trace_limit=limit)


def test_cli_text_trace_and_option_validation(tmp_path):
    source, output, report = [tmp_path / name for name in ("in.txt", "out.txt", "report.json")]
    source.write_text("user [at] example [dot] com", encoding="utf-8")
    assert main([str(source), "--include", "EMAIL", "-o", str(output),
                 "--explain", str(report), "--trace-limit", "5"]) == 0
    assert "overlap_trace" in json.loads(report.read_text())
    for options in (["--trace-limit", "5"], ["--trace-limit", "1001", "--explain", str(report)]):
        with pytest.raises(SystemExit):
            main([str(source), *options])


@pytest.mark.parametrize("mode", [ProcessingMode.STRICT, ProcessingMode.BALANCED, ProcessingMode.PARANOID])
def test_policy_priority_has_its_own_reason_and_report(mode):
    text = "010-2345-6789"
    secondary = RegexDetector(text, label="RRN", risk_level=RiskLevel.CRITICAL, confidence=0.1)
    result = Anonymizer(mode=mode, secondary_detector=secondary, trace_limit=20).process(text)
    report = explain(result, include_trace=True)
    event = next(e for e in report["overlap_trace"]["discarded"] if e["stage"] == "hybrid")
    assert result.text != text
    assert event["candidate"]["label"] == "RRN"
    assert event["blocker"]["label"] == "PHONE"
    assert event["reason"] == "non_blocking_policy_priority"
    assert report["overlap_resolution"].startswith("block_risk_confidence_length_start;")
    assert text not in json.dumps(report)
    without_trace = Anonymizer(mode=mode, secondary_detector=secondary).process(text)
    assert without_trace.text == result.text
    assert explain(without_trace)["overlap_resolution"] == report["overlap_resolution"]
