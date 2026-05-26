from ko_pii.detect import detect_all


def test_runs_all_detectors_on_mixed_text():
    text = (
        "신청인 880101-1234568, 연락처 010-1234-5678, "
        "이메일 user@example.com, IP 192.168.0.1"
    )
    detections = detect_all(text)
    labels = {d.label for d in detections}
    assert {"RRN", "PHONE", "EMAIL", "IP"}.issubset(labels)


def test_no_overlaps_in_output():
    text = "주민번호 880101-1234568"
    detections = detect_all(text)
    sorted_ds = sorted(detections, key=lambda d: d.start)
    for a, b in zip(sorted_ds, sorted_ds[1:]):
        assert a.end <= b.start


def test_include_filter():
    text = "신청인 880101-1234568 연락처 010-1234-5678"
    detections = detect_all(text, include=["RRN"])
    assert {d.label for d in detections} == {"RRN"}


def test_exclude_filter():
    text = "신청인 880101-1234568 연락처 010-1234-5678"
    detections = detect_all(text, exclude=["RRN"])
    assert "RRN" not in {d.label for d in detections}


def test_corp_reg_vs_rrn_partition():
    # 880101-1234568 → RRN takes precedence over CORP_REG anyway by virtue
    # of the corp_reg module deferring to RRN. Make sure detect_all yields
    # only RRN here.
    detections = detect_all("880101-1234568")
    labels = {d.label for d in detections}
    assert "RRN" in labels
    assert "CORP_REG" not in labels
