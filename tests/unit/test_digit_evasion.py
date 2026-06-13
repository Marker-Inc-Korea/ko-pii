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


def test_latin_homoglyph_rrn_detected() -> None:
    # 0→O, 1→l 로 위장한 주민번호.
    assert detect_all("제 주민등록번호는 9OOlOl-l234567 입니다")


def test_normal_english_not_folded() -> None:
    # 'NO'/'ID'/'SOS' 등 정상 영문은 숫자열이 아니므로 폴딩/오탐되지 않아야.
    assert not detect_all("Please say NO to the ID check. SOS is a code.")


def test_devanagari_thai_digits_detected() -> None:
    assert detect_all("주민번호 ९०१०१०-१२३४५६७")          # Devanagari
    assert detect_all("카드 ๔๑๑๑-๑๑๑๑-๑๑๑๑-๑๑๑๑")        # Thai


def test_unicode_dash_separators_detected() -> None:
    assert detect_all("연락처 010–1234–5678")             # EN DASH
    assert detect_all("주민번호 901010—1234567")          # EM DASH
    assert detect_all("연락처 010－1234－5678")            # 전각 하이픈


def test_unicode_dash_in_normal_text_no_fp() -> None:
    assert not detect_all("프로젝트 기간 2020–2021 자료를 검토합니다")


# --- round-4: 고정 숫자체 목록 밖의 비주류 Nd 숫자체도 폴딩되어야 ---

def test_rare_numeral_systems_rrn_detected() -> None:
    # 고정 16개 _DIGIT_BASES 가 놓치던 숫자체 — 이제 전체 Nd 를 unicodedata.decimal 로 환원.
    assert detect_all("주민번호 ᠙᠐᠐᠑᠐᠑-᠑᠒᠓᠔᠕᠖᠗")        # Mongolian (U+1810)
    assert detect_all("주민번호 ߉߀߀߁߀߁-߁߂߃߄߅߆߇")        # N'Ko (U+07C0)
    assert detect_all("카드 ꧔꧑꧑꧑-꧑꧑꧑꧑-꧑꧑꧑꧑-꧑꧑꧑꧑")    # Javanese (U+A9D0): 4111…
    assert detect_all("주민번호 ꘩꘠꘠꘡꘠꘡-꘡꘢꘣꘤꘥꘦꘧")        # Vai (U+A620)


def test_fullwidth_and_rare_numeral_no_normal_fp() -> None:
    # 일반 한글 문장은 비주류 숫자체 폴딩 추가에도 오탐되지 않아야.
    assert not detect_all("회의는 다음 주 화요일 오후에 진행됩니다")
