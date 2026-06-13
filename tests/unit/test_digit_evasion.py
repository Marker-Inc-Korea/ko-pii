"""비ASCII 숫자 PII 검출 우회 회귀 — 라운드2 레드팀 발견.

주민/사업자 번호를 Arabic-Indic 숫자(٩٠٠١٠١)로 적으면 NFKC 가 펴지 않아 검출을
회피하던 갭. unicode_norm 이 Arabic-Indic → ASCII 로 폴딩하도록 수정.
"""
from __future__ import annotations

from ko_pii import detect_all


def test_arabic_indic_rrn_detected() -> None:
    assert detect_all("제 주민등록번호는 ٩٠٠١٠١-١٢٣٤٥٦٧ 입니다")


def test_arabic_indic_biz_detected() -> None:
    assert detect_all("사업자등록번호 ٢٢٠-٨١-٦٢٥١٧")


def test_ascii_digits_still_detected() -> None:
    assert detect_all("제 번호는 900101-1234567 입니다")


def test_normal_text_unaffected() -> None:
    assert not detect_all("안녕하세요 반갑습니다 오늘 날씨가 좋네요")
