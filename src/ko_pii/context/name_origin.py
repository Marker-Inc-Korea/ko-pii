"""이름 문자열의 표기 형태에 대한 레거시 보조 태그 — 룰 기반.

이 태그는 국적·시민권·실제 출신 또는 보호 대상 여부의 판정이 아니다. 기본 가명화는
foreign/unknown 태그를 이유로 이름을 제외하지 않는다. 업무의 제외 정책으로 사용하면
실제 개인정보를 놓칠 수 있다. KLUE의 별도 korean_only 표본 제한도 일반 성능이 아니다.

분류 휴리스틱 (Korean 두음법칙·음운 + surname 사전):
- 한국 성씨 시작 + 2~4자 → korean
- 5자 이상 한글 → foreign 태그 (긴 한국 이름도 이 태그를 받는 한계가 있음)
- 성씨 사전에 없는 특정 첫 음절 (라/러/로/루/류/리 등) → foreign 태그
- 성씨 사전에 없고 지정 음절 (스·쇼·츠·체·트·프 등) 포함 → foreign 태그

휴리스틱 결과와 반환 문자열은 기존 호환성을 위해 유지한다. 긴 한글 이름과 한자·
로마자 표기만으로 실제 사람의 출신을 알아낼 수 없다.
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

    # Preserve the legacy length-based tag; long Korean names also take this branch.
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
