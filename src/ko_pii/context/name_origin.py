"""한국 인명 vs 외국인명 origin 분류 — 룰 기반.

본 라이브러리의 가명화 *주 대상* 은 한국 시민 (민원인·신청인·환자 등). 외국인명
(예: 왕가위·소피마르소·짐캐리) 은 가명화 정책 *대상 아님* 으로 분류하여:

1. 평가 시 — KLUE-NER 같은 외부 벤치마크에서 외국인 PS 라벨 제외 → 더 정직한
   recall 측정
2. 검출 시 — origin tag 부착으로 사용자가 *후속 필터* 가능

분류 휴리스틱 (Korean 두음법칙·음운 + surname 사전):
- 한국 성씨 시작 + 2~4자 → korean
- 5자 이상 한글 → 거의 외래어 (한국 이름은 통상 2~4자)
- 'ㄹ' 초성 음절 시작 → 한국어 두음법칙상 외래어 우선 (라/러/로/루/류/리)
- 외래어 특이 음절 (스·쇼·츠·체·트·프 등) 다수 포함 → foreign

법적·정책 근거: 본 라이브러리의 가명화 대상은 한국 개인정보보호법상 *한국인
정보 주체*. 외국인 식별 정보는 FRN (외국인등록번호) 카테고리가 별도 담당.
"""
from __future__ import annotations


# 한국어 두음법칙에 의해 어두에 쓰이지 않는 음절 — 외래어 강한 신호
_FOREIGN_INITIAL_SYLLABLES: frozenset[str] = frozenset({
    "라", "랴", "러", "려", "로", "료", "루", "류", "르", "리",  # ㄹ 두음
    "냐", "녀", "뇨", "뉴", "니",  # ㄴ 두음 (일부)
})

# 한국 이름에 거의 없는 외래어 빈출 음절 (음운적으로 어색)
_FOREIGN_TYPICAL_SYLLABLES: frozenset[str] = frozenset({
    # 일본·영어 음역 빈출
    "쉬", "츠", "체", "테", "토", "트", "프", "푸", "퍼", "팻", "쳇",
    "케", "캐", "쿠", "쿵", "콩", "콘",
    "베", "뱀", "뷔",
    "마", "메", "모", "무", "므",  # 일부 음절 (한국 이름에도 일부 있어 약한 신호)
    "샤", "쇼", "슈", "솨",
    "샹",
    # (제거: 뷔트·비스·위치·샹송 — 매처가 단일 글자만 보므로 다글자 항목은 매칭 불가 dead)
    # 단순화: 한국 이름 잘 안 쓰는 음절들
    "스",
})


def classify_name_origin(name: str) -> str:
    """Return 'korean', 'foreign', or 'unknown'.

    >>> classify_name_origin('홍길동')
    'korean'
    >>> classify_name_origin('소피마르소')
    'foreign'
    >>> classify_name_origin('알파치노')
    'foreign'
    >>> classify_name_origin('짐캐리')
    'foreign'
    """
    if not name:
        return "unknown"
    if not all("가" <= c <= "힣" for c in name):
        return "unknown"

    # 5자 이상 한글 = 거의 외래어 (한국 이름 typical max 4자)
    # surname 시작이어도 5자 이상이면 외래어 음역으로 봄 (예: "조지부시")
    if len(name) >= 5:
        return "foreign"

    from ko_pii.dictionaries.surnames import surname_prefix_len
    sp = surname_prefix_len(name)

    # 한국 성씨 + 2~4자 = 한국 이름 (성씨 판정을 먼저 — 류현진·라미란·노무현 등
    # ㄹ/ㄴ 두음 성씨가 아래 외래어-두음 규칙에 걸려 'foreign' 으로 오분류되던 문제 수정)
    if sp > 0 and 2 <= len(name) <= 4:
        return "korean"

    # ㄹ/ㄴ 두음 시작 — 한국 이름은 거의 이렇게 시작 안 함 (성씨가 아닌 경우만)
    if name[0] in _FOREIGN_INITIAL_SYLLABLES:
        return "foreign"

    # 외래어 빈출 음절 다수 포함 (surname 없는 케이스만)
    if sp == 0:
        foreign_count = sum(1 for c in name if c in _FOREIGN_TYPICAL_SYLLABLES)
        if foreign_count >= 1:
            return "foreign"

    return "unknown"


def is_korean_name(name: str) -> bool:
    return classify_name_origin(name) == "korean"


def is_foreign_name(name: str) -> bool:
    return classify_name_origin(name) == "foreign"
