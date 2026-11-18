"""Detector pass ordering and overlap eligibility remain unchanged by indexing."""
import pytest

from ko_pii.core._interval_index import ForwardIntervalIndex
from ko_pii.patterns import address, birth


class ScanIndex:
    def __init__(self, spans):
        self.spans = list(spans)

    def overlaps(self, start, end, *, margin=0):
        return any(start < old_end + margin and old_start - margin < end
                   for old_start, old_end in self.spans)

    def add(self, start, end):
        self.spans.append((start, end))


@pytest.mark.parametrize("module,source", [
    (address, "주소: 서울특별시 강남구 테헤란로 152 (역삼동) B1층\n"
              "주소: 경기도 성남시 분당구 정자동 12-3, 101동 1202호\n"
              "거주: 해운대구 우동 123\n" + "공개 정보 " * 20 + "\n주소: 부산광역시\n"),
    (birth, "생년월일: 1988년 1월 1일\n생년월일: 1991-02-03\n"
            "생일 1992.03.04\n1988년생\n생년월일: 91/02/03\n시행일자: 2026-05-21"),
])
def test_detector_matches_the_naive_overlap_oracle(monkeypatch, module, source):
    indexed = list(module.detect(source * 40))
    monkeypatch.setattr(module, "ForwardIntervalIndex", ScanIndex)
    assert list(module.detect(source * 40)) == indexed


def test_nested_intervals_and_touching_edges():
    index = ForwardIntervalIndex([(0, 1000), (100, 110), (200, 210)])
    assert index.overlaps(500, 501)
    assert not index.overlaps(1000, 1001)
    assert index.overlaps(1000, 1001, margin=1)


@pytest.mark.parametrize("operation", ["query", "add"])
def test_backward_use_is_rejected_instead_of_silently_misclassifying(operation):
    index = ForwardIntervalIndex([])
    index.overlaps(10, 20)
    with pytest.raises(ValueError, match="move forward"):
        if operation == "query":
            index.overlaps(9, 20)
        else:
            index.add(9, 20)
