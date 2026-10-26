"""Synthetic regressions for output, batch configuration and buffer boundaries."""
import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.cli import main
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.integrations.custom import RegexDetector
from ko_pii.streaming import PreForwardAnonymizer, StreamBufferClosed


@pytest.mark.parametrize("mode", [ProcessingMode.STRICT, ProcessingMode.BALANCED,
                                 ProcessingMode.PARANOID])
@pytest.mark.parametrize("confidence", [0.1, 0.49])
def test_nonblocking_secondary_cannot_unmask_phone(mode, confidence):
    source = "010-2345-6789"
    secondary = RegexDetector(source, label="RRN", risk_level=RiskLevel.CRITICAL,
                              confidence=confidence)
    result = Anonymizer(mode=mode, secondary_detector=secondary, trace_limit=20).process(source)
    assert source not in result.text
    assert result.detections[0].detection.label == "PHONE"
    assert result.overlap_trace is not None


@pytest.mark.parametrize("secondary_conf,expected", [(0.59, "REVIEW"), (0.99, "BLOCK")])
def test_fallback_uses_covering_same_label_review_confirmation(monkeypatch, secondary_conf, expected):
    import ko_pii.anonymizer as module
    source = "010-2345-6789"
    primary = DetectionResult("PHONE", source, 0, len(source), RiskLevel.HIGH, 0.6)
    monkeypatch.setattr(module, "detect_all", lambda *a, **k: [primary])
    secondary = RegexDetector(source, label="PHONE", confidence=secondary_conf)
    result = Anonymizer(secondary_detector=secondary, merge_mode="fallback_secondary").process(source)
    assert result.detections[0].action.value == expected
    assert primary.confidence == 0.6


@pytest.mark.parametrize("pattern,label", [("2345", "PHONE"), ("010-2345-6789", "RRN")])
def test_fallback_does_not_promote_partial_or_other_label(monkeypatch, pattern, label):
    import ko_pii.anonymizer as module
    source = "010-2345-6789"
    primary = DetectionResult("PHONE", source, 0, len(source), RiskLevel.HIGH, 0.6)
    monkeypatch.setattr(module, "detect_all", lambda *a, **k: [primary])
    result = Anonymizer(secondary_detector=RegexDetector(pattern, label=label),
                        merge_mode="fallback_secondary").process(source)
    assert result.detections[0].action.value == "REVIEW"


@pytest.mark.parametrize("confidence,expected", [(0.99, "REVIEW"), (1.0, "BLOCK")])
def test_cross_validation_penalty_follows_strict_threshold(confidence, expected):
    secondary = RegexDetector("XQZtoken", label="PERSON", confidence=confidence)
    result = Anonymizer(secondary_detector=secondary, merge_mode="cross_validation").process("XQZtoken")
    assert result.detections[0].action.value == expected
    assert result.detections[0].detection.confidence == confidence * 0.7


def test_audit_never_transforms_secondary():
    secondary = RegexDetector("XQZtoken", label="PERSON")
    for mode in ("union", "cross_validation", "fallback_secondary"):
        assert Anonymizer(mode=ProcessingMode.AUDIT, secondary_detector=secondary,
                          merge_mode=mode).process("XQZtoken").text == "XQZtoken"


@pytest.mark.parametrize("workers", [1, 2])
def test_batch_preserves_config_and_performs_no_writes(tmp_path, workers):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    (inputs / "a.txt").write_text("demo@example.com", encoding="utf-8")
    (inputs / "z.txt").write_text("other@example.com", encoding="utf-8")
    config = outputs / "z.txt"
    config.write_text("Acme\n", encoding="utf-8")
    result = main([str(inputs), "--batch", "--output-dir", str(outputs),
                   "--person-exclusions-file", str(config), "--workers", str(workers),
                   "--json-summary"])
    assert result != 0
    assert config.read_text(encoding="utf-8") == "Acme\n"
    assert not (outputs / "a.txt").exists()


def test_empty_chunks_do_not_consume_memory_but_closed_buffers_stay_closed():
    stream = PreForwardAnonymizer(max_chars=1)
    for _ in range(10_000):
        stream.feed("")
    assert stream._chunks == []
    assert stream.status.buffered_chars == 0
    stream.feed("x")
    assert stream.finalize().text == "x"
    with pytest.raises(StreamBufferClosed):
        stream.feed("")
