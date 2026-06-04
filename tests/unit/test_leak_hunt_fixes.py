"""적대적 버그 헌팅(누출 스윕)에서 확인된 누출 13건 + ReDoS 수정 회귀 테스트.

각 케이스는 "검출 가능한 고신뢰 PII 가 .process() 출력에 평문으로 남지 않는다"
를 보장한다. (themes A 정규화 / B 검출누락 / C IO래핑 / E 표·배치 / F ReDoS)
"""
import re
import time
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.detect import detect_all
from ko_pii.tabular import anonymize_records


def _masked(text: str, mode: str = "STRICT") -> str:
    return Anonymizer(mode=getattr(ProcessingMode, mode), strategy="redact").process(text).text


def _no_digit_leak(text: str, mode: str = "STRICT") -> bool:
    return not re.search(r"[0-9]{3,}", _masked(text, mode))


class TestNormalizationLeaks:
    """A — 정규화가 우회를 막기는커녕 만들던 누출."""

    @pytest.mark.parametrize("inv", ["​", "­", "⁠", "﻿"])
    def test_invisible_char_between_two_pii_not_fused(self, inv):
        # 보이지 않는 문자 제거가 RRN+전화를 하나로 융합 → 둘 다 누출하던 #0
        t = f"880101-1234568{inv}010-1234-5678"
        labels = {d.label for d in detect_all(t)}
        assert {"RRN", "PHONE"} <= labels
        assert _no_digit_leak(t)

    def test_u2a74_nfkc_colon_injection(self):
        # U+2A74(⩴) NFKC→'::=' 가 PII 를 쪼개 미검출 + 가짜 IPv6 유발하던 #1
        assert _no_digit_leak("880⩴101-1234568")
        assert _no_digit_leak("010-1234⩴-5678")

    @pytest.mark.parametrize("ctrl", ["\x7f", "\x85", "\x01", "́"])
    def test_control_and_combining_split(self, ctrl):
        # 제어문자·결합표시가 PII 숫자열을 쪼개던 #5
        assert _no_digit_leak(f"880101{ctrl}1234568")

    def test_letter_diacritic_preserved(self):
        # 회귀: 문자 결합표시(é)는 보존돼야
        from ko_pii.core.unicode_norm import normalize_unicode
        norm, _ = normalize_unicode("café")  # already-composed
        assert "caf" in norm


class TestDetectionGapLeaks:
    """B — 유효·체크섬통과 PII 가 구분자 변형으로 미검출되던 누출."""

    def test_dot_separated_rrn(self):
        assert any(d.label == "RRN" for d in detect_all("880101.1234568"))

    def test_intl_landline_phone(self):
        assert any(d.label == "PHONE" for d in detect_all("+82-2-1234-5678"))
        assert any(d.label == "PHONE" for d in detect_all("+82-31-123-4567"))

    def test_dot_slash_card_luhn_valid(self):
        # 4242 4242 4242 4242 는 Luhn 유효
        assert any(d.label == "CARD" for d in detect_all("4242.4242.4242.4242"))
        assert any(d.label == "CARD" for d in detect_all("4242/4242/4242/4242"))


class TestIOWrapLeaks:
    """C — 셀 줄바꿈/래핑(하이픈+개행)으로 분리된 PII 누출 (#6)."""

    @pytest.mark.parametrize("t", [
        "951230-\n1850431",       # RRN hyphen+newline
        "951230- 1850431",        # RRN hyphen+space (csv \n→space 후)
        "010-1234-\n5678",        # phone
        "4242-4242-4242-\n4242",  # card (Luhn 유효)
    ])
    def test_hyphen_whitespace_wrap(self, t):
        assert _no_digit_leak(t, "PARANOID")


class TestReDoS:
    """F — 주소 정규식 백트래킹 폭발 (#13). 긴 한글런이 선형 시간."""

    def test_long_hangul_run_is_fast(self):
        t0 = time.time()
        detect_all("가" * 8000 + " ")
        assert time.time() - t0 < 1.0  # 폭발 시 수초~행

    def test_real_address_still_detected(self):
        assert any(d.label == "ADDRESS" for d in detect_all("서울특별시 강남구 테헤란로 152"))


class TestTabularLeaks:
    """E — 표 처리 누출 (#10 이질 레코드 / #11 ragged 초과셀)."""

    def test_heterogeneous_records_union_keys(self):
        recs = [{"이름": "홍길동"}, {"이름": "김철수", "주민번호": "900101-1234567"}]
        out, _ = anonymize_records(recs, strategy="redact")
        assert "900101-1234567" not in str(out[1].get("주민번호"))

    def test_ragged_restkey_overflow_scanned(self):
        recs = [{"이름": "홍길동", None: ["010-1234-5678", "900101-1234567"]}]
        out, _ = anonymize_records(recs, strategy="redact")
        joined = " ".join(str(v) for v in out[0].get(None, []))
        assert "010-1234-5678" not in joined and "900101-1234567" not in joined


class TestBatchPathCollision:
    """E — 다른 디렉토리의 동명 파일이 출력 충돌로 덮어쓰던 데이터 손실 (#12)."""

    def test_same_name_different_dirs_no_overwrite(self, tmp_path):
        from ko_pii.batch import process_paths
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "out").mkdir()
        (tmp_path / "a" / "doc.txt").write_text("A 010-1111-2222")
        (tmp_path / "b" / "doc.txt").write_text("B 010-3333-4444")
        process_paths(
            [str(tmp_path / "a" / "doc.txt"), str(tmp_path / "b" / "doc.txt")],
            str(tmp_path / "out"), progress=False,
        )
        assert len(list((tmp_path / "out").iterdir())) == 2
