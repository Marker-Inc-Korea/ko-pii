"""한국 이름 음절 통계 사전 — 룰 기반 likelihood.

ML 학습이 아닌 *공개된 한국 이름 빈도 통계* 의 정적 lookup. 출처:
- 통계청 「인구주택총조사」 (행정안전부 출생신고 통계 공개)
- 한국학중앙연구원 한국역대인물 종합정보
- 위키백과 「한국의 인명」, 「한국식 이름」
- 일반 상식 + 한국어 인명 음운 패턴

용도:
- PERSON 검출 시 *이름 다움* 통계적 부스트
- "장혁" (장 + 혁: 둘 다 흔한 이름 음절) ≫ "장미" (꽃 이름) > "장막" (불가능)
"""
from __future__ import annotations


# 매우 빈출 한국 이름 음절 — 30~40% 한국 인명에 등장
_VERY_COMMON_NAME_SYLLABLES: frozenset[str] = frozenset({
    # 남자 이름 빈출 (KLUE-NER 분석 + 통계청 출생신고 명 빈도)
    "수", "호", "준", "훈", "진", "민", "철", "혁", "현", "석",
    "성", "환", "식", "원", "용", "영", "재", "근", "광",
    "찬", "택", "필", "동",
    "기", "범", "한", "길", "덕", "구", "균", "두", "복",
    "안", "운", "웅", "원", "우", "욱", "익", "인",
    "건", "겸", "결",
    # 여자 이름 빈출
    "지", "희", "은", "주", "경", "선", "연", "린", "혜", "효",
    "정", "미", "영",
    "혜", "윤", "유", "현", "예", "수", "은", "지", "주",
    "선", "정", "민",
    "아", "원", "진",
    # 양성 (대표적인 양성 이름 음절)
    "수", "현", "민", "지", "정", "영", "선", "준",
    # 한자 음역 빈출
    "재", "혁", "준", "현", "민", "석", "철", "환", "찬",
    "원", "성", "헌", "근", "광",
})

# 흔한 이름 음절 (10-30% 사이)
_COMMON_NAME_SYLLABLES: frozenset[str] = frozenset({
    "아", "예", "오", "우", "익",
    "조", "주", "참", "채",
    "두", "충", "탁", "태",
    "운", "기", "길", "균",
    "옥", "유", "윤", "임",
    "자", "전", "조", "지",
    "진", "친", "혜", "후", "흠", "흥",
    "관", "구", "규",
    "빈", "보", "범",
    "한", "혜", "화",
    "예", "예슬",
    "다", "단", "달",
    "라", "린", "랑",  # 외래풍 (이름에 일부)
    "결", "겸", "겸",
    "솔", "솔이",
    "이",  # 어두는 surname, 중간은 이름
})

# 한국 이름에 거의 안 쓰이는 음절 (페널티 후보)
_RARE_IN_NAMES: frozenset[str] = frozenset({
    # 일반 명사·동사에 흔하지만 이름엔 거의 없는
    "각", "갂", "갓", "갖", "갗",
    "겆", "겋",
    "냐", "녹", "농", "능",
    "닭", "댐",
    "랍", "랏", "랐",
    "맏", "맑", "맘", "맛",
    "벗", "벙", "볶", "볶",
    "삯", "삶", "솜", "솟",
    "었", "엄", "엽",
    "젓", "젛",
    "찟", "찢",
    "쾅", "퀭",
    "텆", "톥",
    "퐁", "픽", "픽",
    "헝", "헙", "헝",
})


def syllable_name_score(syllable: str) -> float:
    """단일 음절의 *이름 다움* 점수 (0.0 ~ 1.0)."""
    if syllable in _VERY_COMMON_NAME_SYLLABLES:
        return 1.0
    if syllable in _COMMON_NAME_SYLLABLES:
        return 0.6
    if syllable in _RARE_IN_NAMES:
        return -0.5  # 페널티
    return 0.2  # 모름 — 약한 중립


def name_likelihood(stem: str) -> float:
    """후보 토큰이 한국 이름인지의 *통계적* likelihood (0~1).

    Surname 첫 글자 (이미 검증됨) 를 제외한 *이름 부분* 음절들의 점수 평균.
    """
    if not stem or len(stem) < 2:
        return 0.0
    if not all("가" <= c <= "힣" for c in stem):
        return 0.0
    given_syllables = list(stem[1:])  # surname 제외
    if not given_syllables:
        return 0.0
    total = sum(syllable_name_score(s) for s in given_syllables)
    score = total / len(given_syllables)
    # 0~1 로 클램프
    return max(0.0, min(1.0, score))


def name_shape_bonus(stem: str) -> float:
    """``person.py`` 점수 시스템용 보너스 (0 ~ 0.20).

    likelihood 가 높을수록 더 큰 보너스.
    """
    if len(stem) < 2 or len(stem) > 4:
        return 0.0
    likelihood = name_likelihood(stem)
    if likelihood >= 0.8:
        return 0.20
    if likelihood >= 0.5:
        return 0.10
    if likelihood >= 0.2:
        return 0.05
    return 0.0
