"""일반화 (Generalization) — 정밀도를 낮춰 식별 위험을 떨어뜨림.

비식별 조치 가이드라인의 "일반화 (Generalization)" 기법:
- 연속형(나이, 날짜) → 구간화
- 위치(주소) → 상위 행정구역
- 직업/소득 → 범주
"""
from ko_pii.generalization.age import generalize_age
from ko_pii.generalization.date import generalize_date
from ko_pii.generalization.address import generalize_address
from ko_pii.generalization.occupation import generalize_occupation

__all__ = [
    "generalize_age",
    "generalize_date",
    "generalize_address",
    "generalize_occupation",
]
