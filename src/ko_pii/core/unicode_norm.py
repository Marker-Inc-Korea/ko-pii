"""유니코드 정규화 — 전각/호환문자 폴딩 + 보이지 않는 문자 제거 (offset 보존).

PII 검출 우회 차단:
- **전각 숫자/영문**: ``０１０`` → ``010``, ``ＡＢ`` → ``AB`` (NFKC)
- **호환 형태**: ``①`` → ``1``, ``㈜`` → ``(주)``, ``㎡`` → ``m2``
- **제로폭/보이지 않는 문자 삽입**: 제로폭 공백(U+200B), 조이너(ZWJ/ZWNJ),
  BOM(U+FEFF), 소프트하이픈(U+00AD), 방향 마크(LRM/RLM) 등 → 제거

``detect.detect_all`` 진입점에서 **기본 적용**되며, 검출 결과 offset 은
원본 문자열 기준으로 역매핑된다. 외부 의존성 없음 (표준 ``unicodedata``).

문자 단위로 처리하는 이유: 문자열 전체 NFKC 는 길이를 바꿔(``ﬁ``→``fi`` 등)
offset 이 깨진다. 글자별 폴딩 + offset_map 으로 원본 위치를 보존한다.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ko_pii.core.types import DetectionResult

# 보이지 않는/제로폭/방향 문자 — 삽입형 우회 벡터.
# 소프트하이픈(00AD), 제로폭 공백·조이너·방향마크(200B–200F),
# 방향 임베딩/오버라이드/아이솔레이트·word joiner(202A–202E, 2060–206F),
# BOM/ZWNBSP(FEFF).
_INVISIBLE = re.compile(
    # U+2A74(\u2A74) \uCD94\uAC00: NFKC \uD655\uC7A5\uC774 '::=' \uC778 \uC720\uC77C \uBB38\uC790 \u2014 PII \uC22B\uC790\uC5F4\uC5D0 '::' \uC8FC\uC785\uC73C\uB85C
    # RRN/\uC804\uD654\uB97C \uCABC\uAC1C \uBBF8\uAC80\uCD9C\uC2DC\uD0A4\uACE0 \uAC00\uC9DC IPv6 \uB97C \uC720\uBC1C. \uC81C\uAC70\uD558\uBA74 \uC22B\uC790\uC5F4\uC774 \uC7AC\uACB0\uD569\uB428.
    # C0 \uC81C\uC5B4\uBB38\uC790(\uD0ED\t\u00B7\uC904\uBC14\uAFC8\n\u00B7CR\r \uC81C\uC678)\u00B7DEL\u00B7C1 \uCD94\uAC00: PII \uC22B\uC790\uC5F4 \uD55C\uAC00\uC6B4\uB370 \uB07C\uBA74
    # \uAC80\uCD9C\uC744 \uCABC\uAC1C\uB294 \uC6B0\uD68C. XML(HWPX/XLSX) \uCD94\uCD9C \uD14D\uC2A4\uD2B8\uC5D0 \uC0B4\uC544\uB0A8\uB294 \uCF00\uC774\uC2A4 \uD3EC\uD568.
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    r"\u00AD\u200B-\u200F\u202A-\u202E\u2060-\u206F\u2A74\uFEFF]"
)

# \uACB0\uD569\uD45C\uC2DC(nonspacing marks) \u2014 \uC22B\uC790 \uC0AC\uC774\uC5D0 \uB07C\uBA74 PII \uB97C \uCABC\uAC1C\uB294 \uC6B0\uD68C. \uD074\uB7EC\uC2A4\uD130 NFKC
# \uB2E8\uACC4\uC5D0\uC11C \uBB38\uC790\uC5D4 \uBCF4\uC874(\u00E9)\u00B7\uC22B\uC790\uC5D4 \uC81C\uAC70. fast-path \uAC00 \uACB0\uD569\uD45C\uC2DC \uD14D\uC2A4\uD2B8(\uC774\uBBF8 NFKC \uB77C\uB3C4)\uB97C
# \uAC74\uB108\uB6F0\uC9C0 \uC54A\uB3C4\uB85D \uBCC4\uB3C4 \uAC80\uC0AC\uD55C\uB2E4.
_COMBINING = re.compile(
    r"[\u0300-\u036F\u0483-\u0489\u0591-\u05BD\u0610-\u061A"
    r"\u064B-\u065F\u0670\u06D6-\u06DC\u1AB0-\u1AFF\u1DC0-\u1DFF"
    r"\u20D0-\u20FF\uFE20-\uFE2F]"
)

# \uBE44ASCII \uC22B\uC790 \u2192 ASCII \uC22B\uC790 \uD3F4\uB529. NFKC \uB294 \uC774\uB4E4\uC744 \uD3B4\uC9C0 \uC54A\uC73C\uBBC0\uB85C(\uC815\uADDC\uD615) \uC9C1\uC811 \uB9E4\uD551\uD55C\uB2E4.
# \uC8FC\uBBFC/\uC0AC\uC5C5\uC790/\uCE74\uB4DC \uBC88\uD638\uB97C Arabic-Indic \uC22B\uC790\uB85C \uC801\uC740 \uAC80\uCD9C \uC6B0\uD68C\uB97C \uCC28\uB2E8. 1:1 \uCE58\uD658\uC774\uB77C
# offset_map \uC774 \uBCF4\uC874\uB41C\uB2E4.
# \uBE44ASCII \uC22B\uC790\uCCB4(\uC544\uB78D/\uB370\uBC14\uB098\uAC00\uB9AC/\uBCB5\uACE8/\uD0DC\uAD6D \uB4F1) \u2192 ASCII, \uADF8\uB9AC\uACE0 \uB2E4\uC591\uD55C \uD558\uC774\uD508\u00B7\uB300\uC2DC\u00B7
# \uB9C8\uC774\uB108\uC2A4 \u2192 ASCII '-'. NFKC \uAC00 \uD3B4\uC9C0 \uC54A\uB294 \uAC80\uCD9C \uC6B0\uD68C\uB97C \uC9C1\uC811 \uB9E4\uD551\uD55C\uB2E4(1:1, offset \uBCF4\uC874).
# \uBAA8\uB4E0 \uC720\uB2C8\uCF54\uB4DC Nd(\uC2ED\uC9C4 \uC22B\uC790) \u2192 ASCII \uD3F4\uB529. \uACE0\uC815 16\uAC1C \uC22B\uC790\uCCB4 \uD558\uB4DC\uCF54\uB529\uC740 \uBABD\uACE8/Vai/
# N'Ko/\uC790\uBC14 \uB4F1 NFKC \uAC00 \uD3B4\uC9C0 \uBABB\uD558\uB294 \uC22B\uC790\uCCB4\uB97C \uB193\uCCE4\uB2E4 \u2014 Nd \uB294 \uC815\uC758\uC0C1 0\u20139 \uAC12\uC744 \uAC00\uC9C0\uBBC0\uB85C
# ``unicodedata.decimal`` \uB85C 1:1 \uD658\uC6D0(\uAE38\uC774 \uBD88\uBCC0 \u2192 offset \uBCF4\uC874). \uC0C1\uD55C U+1FFFF: \uD604\uC7AC
# \uC720\uB2C8\uCF54\uB4DC\uC758 \uCD5C\uC0C1\uC704 Nd(U+1FBF9, Segmented Digits)\uB97C \uB36E\uC73C\uBA74\uC11C import \uBE44\uC6A9\uC744 \uC904\uC778\uB2E4.
_NONASCII_DIGIT_FOLD: dict[str, str] = {
    chr(cp): str(unicodedata.decimal(chr(cp)))
    for cp in range(0x80, 0x20000)
    if unicodedata.category(chr(cp)) == "Nd"
}
_DASH_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2015\u2043\u2212\uFE58\uFE63\uFF0D"
_CHAR_FOLD: dict[str, str] = {
    **_NONASCII_DIGIT_FOLD,
    **{c: "-" for c in _DASH_CHARS},
}
# fast-path \uAC80\uC0AC\uC6A9: _CHAR_FOLD \uC758 \uBAA8\uB4E0 \uBB38\uC790(\uBE44ASCII \uC22B\uC790 + \uB300\uC2DC)\uB97C \uC7A1\uB294 \uBB38\uC790\uD074\uB798\uC2A4\uB97C
# \uC790\uB3D9 \uC0DD\uC131 \u2014 \uC22B\uC790\uCCB4 \uBAA9\uB85D\uACFC regex \uAC00 \uC5B4\uAE0B\uB0A0 \uC77C\uC774 \uC5C6\uB2E4.
_FOLD_DIGIT = re.compile("[" + "".join(re.escape(c) for c in _CHAR_FOLD) + "]")

# \uB77C\uD2F4 \uAE00\uB9AC\uD504\uB85C \uC704\uC7A5\uD55C \uC22B\uC790(O\u21920, l\u21921 \u2026). \uC815\uC0C1 \uC601\uBB38(NO/ID/SOS)\uC744 \uAE68\uC9C0 \uC54A\uB3C4\uB85D
# '\uC22B\uC790 2\uAC1C \uC774\uC0C1 + \uD638\uBAB0\uB85C\uADF8 1\uAC1C \uC774\uC0C1'\uC73C\uB85C \uC774\uB904\uC9C4 \uC22B\uC790\uC5F4 \uD1A0\uD070\uC5D0\uC11C\uB9CC \uD3F4\uB529\uD55C\uB2E4.
# \uC8FC\uBBFC/\uCE74\uB4DC/\uC0AC\uC5C5\uC790\uBC88\uD638\uB97C 'l234567' \uCC98\uB7FC \uC801\uC740 \uAC80\uCD9C \uC6B0\uD68C\uB97C \uCC28\uB2E8. 1:1 \uCE58\uD658(\uAE38\uC774 \uBD88\uBCC0)
# \uC774\uB77C offset_map \uC774 \uBCF4\uC874\uB41C\uB2E4.
_DIGIT_HOMOGLYPH: dict[str, str] = {
    "O": "0", "o": "0", "Q": "0", "l": "1", "I": "1", "|": "1",
    "S": "5", "B": "8", "Z": "2", "G": "6",
}
_DIGIT_HG_CHARS = "".join(re.escape(c) for c in _DIGIT_HOMOGLYPH)
_DIGIT_HG_TOKEN = re.compile(rf"[0-9{_DIGIT_HG_CHARS}][0-9{_DIGIT_HG_CHARS}\-\u2010-\u2015]*")


def _fold_digit_homoglyphs(text: str) -> str:
    """\uC22B\uC790\uC5F4 \uD1A0\uD070 \uC548\uC758 \uB77C\uD2F4 \uD638\uBAB0\uB85C\uADF8\uB97C \uC22B\uC790\uB85C \uD3F4\uB529(1:1, \uAE38\uC774 \uBD88\uBCC0)."""

    def repl(m: re.Match[str]) -> str:
        s = m.group(0)
        digits = sum(c.isdigit() for c in s)
        hg = sum(c in _DIGIT_HOMOGLYPH for c in s)
        if digits >= 2 and hg >= 1:
            return "".join(_DIGIT_HOMOGLYPH.get(c, c) for c in s)
        return s

    return _DIGIT_HG_TOKEN.sub(repl, text)


def needs_normalization(text: str) -> bool:
    """\uC815\uADDC\uD654(\uC6B0\uD68C \uCC28\uB2E8)\uAC00 \uD544\uC694\uD55C\uAC00 \u2014 \uBE44ASCII\uC774\uAC70\uB098 \uC81C\uC5B4/\uBCF4\uC774\uC9C0 \uC54A\uB294 \uBB38\uC790 \uD3EC\uD568.

    ``detect_all`` \uC758 \uC9C4\uC785 \uAC00\uB4DC\uC6A9. ASCII \uC81C\uC5B4\uBB38\uC790(DEL\u00B7C0)\uB3C4 PII \uB97C \uCABC\uAC1C\uB294 \uC6B0\uD68C\uB77C
    ``text.isascii()`` \uB9CC\uC73C\uB860 \uBD80\uC871 \u2014 ``_INVISIBLE`` \uB85C \uC7A1\uB294\uB2E4. \uACB0\uD569\uD45C\uC2DC\uB294 \uBE44ASCII.
    """
    return (not text.isascii()) or bool(_INVISIBLE.search(text))


def _is_conjoining_jamo(ch: str) -> bool:
    """NFD \uBD84\uD574\uD615 \uD55C\uAE00 \uC790\uBAA8(\uCD08\uC131/\uC911\uC131/\uC885\uC131) \uC5EC\uBD80 \u2014 \uD569\uC131 \uD074\uB7EC\uC2A4\uD130\uC5D0 \uD3EC\uD568."""
    return (
        "\u1100" <= ch <= "\u11FF"      # Hangul Jamo
        or "\uA960" <= ch <= "\uA97F"   # Jamo Extended-A
        or "\uD7B0" <= ch <= "\uD7FF"   # Jamo Extended-B
    )


def normalize_unicode(text: str) -> tuple[str, list[int]]:
    """NFKC 폴딩 + 보이지 않는 문자 제거.

    Returns ``(normalized, offset_map)``. ``offset_map[i]`` 는 ``normalized[i]``
    에 대응하는 원본 ``text`` 위치. 변화가 없으면 ``normalized == text`` (offset_map
    은 빈 리스트 — 호출측이 무시).
    """
    # 라틴 호몰로그 숫자 폴딩(1:1, 길이 불변 → offset 보존). 빠른 경로 전에 적용해야
    # 'l234567' 같은 ASCII-호몰로그 우회도 펴진다.
    text = _fold_digit_homoglyphs(text)
    # 빠른 경로: 이미 NFKC 이고 보이지 않는/결합 문자도 없으면 그대로 (no-op).
    # 결합표시는 이미 NFKC 일 수 있어(1+◌́ 는 합성형 없음) 별도 검사 — 빠진 채
    # 건너뛰면 숫자에 붙은 결합표시가 PII 를 쪼개 누출된다.
    if (
        not _INVISIBLE.search(text)
        and not _COMBINING.search(text)
        and not _FOLD_DIGIT.search(text)
        and unicodedata.is_normalized("NFKC", text)
    ):
        return text, []

    out: list[str] = []
    omap: list[int] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _INVISIBLE.match(ch):
            i += 1
            continue
        # 기본 문자 + 뒤따르는 결합표시/한글 자모를 한 클러스터로 묶어 NFKC.
        # 글자별 NFKC 는 NFD 분해형(예: 한글 "홍"=홍, 라틴 "é"=e+´)을 합치지
        # 못해 우회를 허용함 → 클러스터 단위 합성으로 차단. 합성 결과는 모두
        # 클러스터 시작 위치(i)로 매핑한다.
        j = i + 1
        while j < n and (unicodedata.combining(text[j]) or _is_conjoining_jamo(text[j])):
            j += 1
        base_is_alpha = text[i].isalpha()
        for fc in unicodedata.normalize("NFKC", text[i:j]):
            # 숫자/기호 베이스에 NFKC 로 합쳐지지 않고 남은 결합표시(U+0301 등)는
            # PII 를 쪼개는 우회 → 제거. 문자(é=e+´ 등 정상 diacritic)는 보존.
            if not base_is_alpha and unicodedata.combining(fc):
                continue
            out.append(_CHAR_FOLD.get(fc, fc))
            omap.append(i)
        i = j
    return "".join(out), omap


def remap_to_source(
    detections: list["DetectionResult"],
    offset_map: list[int],
    source: str,
) -> list["DetectionResult"]:
    """정규화 텍스트 기준 offset 을 원본 기준으로 역매핑 + ``.text`` 원본 복원.

    ``source[start:end] == .text`` 불변식을 유지하도록 ``.text`` 를 원본
    슬라이스로 다시 설정한다.
    """
    n = len(offset_map)
    out: list[DetectionResult] = []
    for det in detections:
        start = offset_map[det.start] if det.start < n else det.start
        # 검출 끝 = 다음 정규화 글자의 원본 시작 위치(= 마지막 글자 클러스터의 원본 끝).
        # 합성(다대일)·제거(invisible)에도 정확하며, 0길이 검출의 start>end 역전도 방지.
        if det.end < n:
            end = offset_map[det.end]
        elif det.end == n:
            end = len(source)
        else:
            end = det.end
        out.append(replace(det, start=start, end=end, text=source[start:end]))
    return out
