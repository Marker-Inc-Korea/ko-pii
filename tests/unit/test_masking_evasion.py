"""마스킹 회피(masking-evasion) 적대적 레드팀 회귀 — AREA B.

검출 가능한 고위험 PII 가 우회 표기로 ``.process()`` 출력에 평문으로 남으면 그대로
LLM 에 유출된다. 아래 4개 갭은 모두 "마스킹이 원본 PII 를 못 덮던" 누출이다.

GAP 1  자릿수 사이 ASCII 공백 주입 ("8 8 0 1 0 1-1234568", "0 1 0 1 2 3 4 5 6 7 8")
GAP 2  문장 분할 + 필러 ("앞자리 880101 뒷자리 1234567", "880101 다시 1234567")
GAP 3  난독화 이메일 ("hong [at] gmail [dot] com", "hong gildong @ naver . com")
GAP 4  괄호 지역번호 ("(010) 9876-5432")

각 갭마다 (a) 우회가 마스킹된다 + (b) 유사 양성(benign) 케이스는 오탐되지 않는다 를
함께 검증한다(recall-safe).
"""
from __future__ import annotations

import re

import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.detect import detect_all


def _masked(text: str, mode: str = "STRICT") -> str:
    return Anonymizer(mode=getattr(ProcessingMode, mode), strategy="redact").process(text).text


def _no_digit_leak(text: str, mode: str = "STRICT") -> bool:
    """마스킹 후 3자리 이상 연속 숫자가 남지 않아야(원본 PII 미유출)."""
    return not re.search(r"[0-9]{3,}", _masked(text, mode))


def _labels(text: str) -> set[str]:
    return {d.label for d in detect_all(text)}


# --------------------------------------------------------------------------
# GAP 1 — per-digit ASCII-space injection
# --------------------------------------------------------------------------
class TestGap1SpacedDigitInjection:
    @pytest.mark.parametrize("t", [
        "8 8 0 1 0 1-1234568",                 # RRN, 앞 6자리 단일공백 주입
        "9 5 1 2 3 0 - 1 8 5 0 4 3 1",         # RRN, 전부 단일공백 (서식 칸별)
    ])
    def test_spaced_rrn_masked(self, t):
        assert "RRN" in _labels(t)
        assert _no_digit_leak(t)

    def test_spaced_phone_masked(self):
        t = "0 1 0 1 2 3 4 5 6 7 8"
        assert "PHONE" in _labels(t)
        assert _no_digit_leak(t)

    def test_span_covers_original_spaced_text(self):
        # 마스킹 span 이 원본(공백 포함) 전체를 덮어 잔여 자릿수가 없어야.
        out = _masked("주민 8 8 0 1 0 1-1234568 끝")
        assert "주민 [주민등록번호] 끝" == out

    @pytest.mark.parametrize("t", [
        "버전 1.5 - 2024",                      # 버전 문자열
        "좌표 37 126",                          # 2~3자리 그룹 좌표
        "사번 880101 처리완료",                 # 단일 6자리 (EMPLOYEE_ID 이지 RRN 아님)
        "37 126 875 456 좌표",                  # 여러 다자리 그룹
        "값 12 34 56 78 90 합계",               # 2자리 그룹 나열
        "버전 1 5 2 0 2 4 패치",                # 단일공백이지만 6자리(대역 밖)
    ])
    def test_benign_not_collapsed_to_pii(self, t):
        # 산문/좌표/버전은 자릿수 공백 붕괴 대상이 아님 → RRN/PHONE FP 없음.
        labels = _labels(t)
        assert "RRN" not in labels
        assert "PHONE" not in labels

    def test_employee_id_preserved_not_rrn(self):
        # '사번 880101' 은 여전히 EMPLOYEE_ID — 갭1 수정이 이를 RRN 으로 바꾸지 않음.
        assert "EMPLOYEE_ID" in _labels("사번 880101 처리완료")


# --------------------------------------------------------------------------
# GAP 2 — RRN split across sentence with filler
# --------------------------------------------------------------------------
class TestGap2SplitRRN:
    @pytest.mark.parametrize("t", [
        "앞자리 880101 뒷자리 1234567",
        "880101 다시 1234567",
        "주민번호 앞자리 880101 뒷자리 1234567",
        "주민등록번호 880101 그리고 1234568",
    ])
    def test_split_rrn_masked(self, t):
        assert "RRN" in _labels(t)
        assert _no_digit_leak(t)

    def test_checksum_valid_split_high_confidence(self):
        # 880101...1234568 은 체크섬 통과 → confidence 1.0.
        dets = [d for d in detect_all("주민등록번호 880101 그리고 1234568") if d.label == "RRN"]
        assert dets and dets[0].confidence == 1.0

    @pytest.mark.parametrize("t", [
        "880101",                               # 6자리 단독 (파트너 없음)
        "회의 880101 일정 확인",                # 6자리 + 산문, 파트너 없음
        "버전 880101 릴리스 1234567 패치",      # 6+7 이지만 무마커·무재조합필러·체크섬불일치
        "좌표 123456 측정 7890123 종료",        # 무관 두 숫자 (무마커)
    ])
    def test_bare_or_uncontexted_not_flagged(self, t):
        # recall-safe: 무작위 6자리 단독, 또는 맥락 없는 6+7 쌍은 RRN 으로 방출 안 함.
        assert "RRN" not in _labels(t)


# --------------------------------------------------------------------------
# GAP 3 — obfuscated email
# --------------------------------------------------------------------------
class TestGap3ObfuscatedEmail:
    @pytest.mark.parametrize("t,expected", [
        ("hong [at] gmail [dot] com", "hong@gmail.com"),
        ("hong gildong @ naver . com", "honggildong@naver.com"),
        ("user (at) example (dot) org", "user@example.org"),
        ("문의 admin [at] korea (dot) kr 으로", "admin@korea.kr"),
    ])
    def test_obfuscated_email_masked(self, t, expected):
        dets = [d for d in detect_all(t) if d.label == "EMAIL"]
        assert dets, t
        assert dets[0].extra.get("value") == expected
        assert "[이메일]" in _masked(t)
        # 원본 도메인/로컬이 평문으로 남지 않아야.
        assert "gmail" not in _masked(t).replace("[이메일]", "")

    @pytest.mark.parametrize("t", [
        "hong@example.com",
        "kim.cs@gov.kr",
        "user+tag@example.org",
    ])
    def test_normal_email_still_detected(self, t):
        assert "EMAIL" in _labels(t)

    @pytest.mark.parametrize("t", [
        "meet at noon and talk dot point",      # 맨단어 at/dot — 산문
        "버전 1.5 와 2.0 비교",
        "admin at gov dot kr",                  # 맨단어 (보수적으로 미검출)
        "가격은 10 . 5 달러",
        "회의 자료 검토 at 3시 dot 확인",
    ])
    def test_prose_not_email_fp(self, t):
        assert "EMAIL" not in _labels(t)


# --------------------------------------------------------------------------
# GAP 4 — parenthesized area code phone
# --------------------------------------------------------------------------
class TestGap4ParenthesizedPhone:
    @pytest.mark.parametrize("t,ptype", [
        ("(010) 9876-5432", "mobile"),
        ("(02) 1234-5678", "landline"),
        ("(031) 123-4567", "landline"),
        ("(070) 1234-5678", "voip"),
        ("연락처 (010)9876-5432 입니다", "mobile"),
    ])
    def test_paren_phone_masked(self, t, ptype):
        dets = [d for d in detect_all(t) if d.label == "PHONE"]
        assert dets, t
        assert dets[0].extra.get("type") == ptype
        # span 이 여는 괄호부터 덮어 잔여 자릿수가 없어야.
        assert _no_digit_leak(t)

    def test_paren_span_includes_opening_paren(self):
        dets = [d for d in detect_all("(010) 9876-5432") if d.label == "PHONE"]
        assert dets[0].text == "(010) 9876-5432"

    @pytest.mark.parametrize("t", [
        "(2024) 발표자료",
        "(123) 항목 참조",
        "버전 (1.5) 참고",
        "(주) 회사명 제품",
    ])
    def test_paren_non_phone_not_fp(self, t):
        assert "PHONE" not in _labels(t)

    @pytest.mark.parametrize("t", [
        "010-1234-5678",
        "02-1234-5678",
        "070-1234-5678",
        "+82-2-1234-5678",
    ])
    def test_existing_phone_forms_unbroken(self, t):
        assert "PHONE" in _labels(t)
