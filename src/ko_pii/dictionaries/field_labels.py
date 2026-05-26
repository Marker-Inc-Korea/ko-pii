"""공문서 필드 라벨 사전 — "성명: 홍길동" 같은 라벨링 신호.

각 라벨이 등장하면 *바로 뒤* 토큰을 사람 이름 후보로 강하게 부스트.
"""
from __future__ import annotations

# 가장 강한 신호 — 라벨 직후 1~4글자 한글이 거의 항상 이름
FIELD_LABELS_NAME: frozenset[str] = frozenset([
    "성명", "이름", "성함", "이 름",       # 띄어쓰기 포함 변형
    "신청인", "신청자", "민원인", "청구인",
    "기안자", "결재자", "검토자", "보고자",
    "보호자", "대리인", "참석자", "위임자", "수임자",
    "출장자", "응답자", "조사자", "피조사자",
    "당사자", "원고", "피고", "고소인", "피고소인",
    "수신자", "발신자", "참조",
    "환자",
    # 수사·경찰·소방 도메인
    "피의자", "피해자", "용의자", "참고인", "증인", "감정인",
    "신고자", "신고인", "수사관", "조사관",
    "출동대장", "출동자", "구조자",
    # 인사·평가
    "평가자", "피평가자", "면담자", "피면담자",
    "추천인", "피추천인",
])

# 부수적 라벨 (이름 후보 보조)
FIELD_LABELS_AUX: frozenset[str] = frozenset([
    "직책", "직위", "소속", "부서", "기관", "담당자", "담당",
    "연락처", "전화", "휴대전화", "이메일",
    "주민등록번호", "주민번호",
    "주소", "거주지", "주민등록상 주소",
])

FIELD_LABELS: frozenset[str] = FIELD_LABELS_NAME | FIELD_LABELS_AUX


def is_field_label(token: str) -> bool:
    return token in FIELD_LABELS


def is_name_field_label(token: str) -> bool:
    return token in FIELD_LABELS_NAME
