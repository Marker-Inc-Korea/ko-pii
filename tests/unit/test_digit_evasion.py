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


# --- round-5 red-team: conjoining jamo / middle-dot / No-category digits ---

def test_conjoining_jamo_split_pii_detected() -> None:
    # 조합용 한글 자모(U+1100~)를 숫자 사이에 끼워 PII 를 쪼갠 우회.
    assert detect_all("주민등록번호 9001ᄀ01-1234567")
    assert detect_all("외국인등록번호 900101-5ᄀ234567")
    assert detect_all("카드 4111-11ᄀ11-1111-1111")
    assert detect_all("사업자 220-8ᄀ1-62517")


def test_conjoining_jamo_normal_hangul_no_fp() -> None:
    import unicodedata
    assert not detect_all("홍길동 안녕하세요 오늘 회의 자료입니다")
    assert not detect_all(unicodedata.normalize("NFD", "한글 정상 문장입니다"))


def test_middle_dot_separator_detected() -> None:
    assert detect_all("연락처 010·1234·5678 입니다")     # U+00B7
    assert detect_all("주민 900101·1234567 입니다")


def test_no_category_digits_detected() -> None:
    # 원/괄호/딩벳 숫자(category No) — NFKC 가 안 펴므로 digit() 로 환원.
    assert detect_all("제 주민등록번호는 ❾⓿⓿❶⓿❶-❶❷❸❹❺❻❼ 이고")     # negative-circled
    assert detect_all("주민번호 ➈⓪⓪➀⓪➀-➀➁➂➃➄➅➆ 입니다")           # dingbat circled
    assert detect_all("카드번호 ❹❶❶❶-❶❶❶❶-❶❶❶❶-❶❶❶❶")


def test_no_category_fractions_preserved() -> None:
    # 분수(½)·위첨자(²)는 단일 자릿값이 없어 폴딩 제외 → PII 오탐 없음.
    assert not detect_all("½컵 설탕과 ⅓컵 소금을 넣으세요")
    assert not detect_all("면적은 25m² 입니다")


# --- round-5: FRN separator parity with RRN (dot / spaced forms) ---

def test_frn_dot_and_spaced_separators_detected() -> None:
    assert detect_all("외국인등록번호 900101.5234569")
    assert detect_all("외국인등록번호 900101 . 5234569")
    assert detect_all("외국인등록번호 900101  5234569")
    assert detect_all("외국인등록번호 900101-5234569")


# --- round-5 false positives: barcode/IMEI not CARD, version not IP ---

def test_card_length_brand_consistency_no_fp() -> None:
    # 15자리 IMEI(35…)·13자리 EAN 바코드(3·5…)는 카드가 아니다.
    assert not any(d.label == "CARD" for d in detect_all("단말기 IMEI: 353280112345674"))
    assert not any(d.label == "CARD" for d in detect_all("상품 바코드 3685957489060 / 5498174104092"))


def test_real_cards_still_detected() -> None:
    for n in ("378282246310005", "5555555555554444", "4111111111111111",
              "4222222222222", "6011111111111117"):
        assert any(d.label == "CARD" for d in detect_all("카드 " + n)), n


def test_version_string_not_ip() -> None:
    assert not any(d.label == "IP" for d in detect_all("소프트웨어 버전 10.0.19.41 배포"))
    assert not any(d.label == "IP" for d in detect_all("v1.2.3.4 릴리스"))


def test_real_ip_still_detected_after_version_gate() -> None:
    # 'server' 의 'ver' 가 버전 단서로 오인되어 IP 를 누락하면 안 됨(단어 경계).
    assert [d.text for d in detect_all("client 10.0.0.5 → server 10.0.0.10") if d.label == "IP"] == [
        "10.0.0.5", "10.0.0.10",
    ]
    assert any(d.label == "IP" for d in detect_all("서버 IP 192.168.0.100"))


# --- round-6 red-team: slash-homoglyph separators + separator parity + intl (0) ---

def test_slash_homoglyph_separators_detected() -> None:
    assert detect_all("4111⁄1111⁄1111⁄1111")        # U+2044 fraction slash (card)
    assert detect_all("4111／1111／1111／1111")        # U+FF0F fullwidth solidus (NFKC)
    assert detect_all("주민 900101⁄5234567")          # RRN via fraction slash
    assert detect_all("외국인등록번호 900101⁄5234569")  # FRN via fraction slash


def test_corp_reg_separator_parity() -> None:
    assert detect_all("법인등록번호 183008.8390499")   # dot
    assert detect_all("법인등록번호 183008/8390499")   # slash


def test_intl_phone_parenthesized_trunk_zero() -> None:
    assert detect_all("Tel: +82 (0)10 9876 5432")


def test_isbn_not_corp_reg() -> None:
    # GS1 Bookland(978/979) 무구분자 13자리는 도서 바코드 → 법인번호 오탐 금지.
    for t in ("도서 ISBN 9788494548130 절판", "도서 ISBN 9788956609959 (구판)"):
        assert not any(d.label == "CORP_REG" for d in detect_all(t)), t


def test_fraction_still_preserved_round6() -> None:
    # 슬래시 폴딩 추가가 분수 정상 텍스트를 PII 로 오탐하면 안 됨.
    assert not detect_all("½컵 설탕과 ⅓컵 소금을 넣으세요")
