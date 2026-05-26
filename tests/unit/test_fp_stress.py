"""FP stress test — PII 가 *없는* 자연어에서 검출기가 잘못 잡지 않는지 검증.

각 케이스는 실제 한국어 문장 또는 공문서 단편이지만 의도적으로 PII 없음.
검출기가 0건을 반환해야 한다.
"""
from ko_pii.detect import detect_all


_FP_CASES: list[str] = [
    # 일반 회의록·보고서 본문
    "본 사업의 추진 경과는 다음과 같으며, 향후 일정은 추가 협의를 통해 결정한다.",
    "회의 결과 위 사항을 만장일치로 통과하였으며, 후속 조치 계획을 수립한다.",
    "전체 안건 12건 중 9건이 의결되었고, 3건은 다음 회의로 이월하였다.",
    # 일정·숫자 포함 (12자리 PNU, 카드 충돌 위험)
    "다음 회의는 12월 1일 14시 30분에 본부 회의실에서 개최한다.",
    "예산 집행률은 87.5% 로 작년 동기 대비 12.3%p 상승하였다.",
    "총 사업비 1,234,567,890원 중 800억원이 1차로 집행되었다.",
    # 차량 관련 일반 표현 (FP 위험)
    "12가게에 들러 1234원짜리 김밥을 샀다.",
    "12강좌 1234명 수강 신청 마감",
    "강남구 영등포구 등 25개 자치구를 모두 방문하였다.",
    # 주소·시·도 멘션
    "서울특별시는 인구가 가장 많은 광역지자체이며 경기도는 면적이 넓다.",
    "수원시 분당구 가평군 등 경기 지역에서 회의가 진행되었다.",
    # 우편번호 충돌
    "12345678 건의 민원이 접수되었다.",  # 8자리 무관 숫자
    "사건번호 99001 보고서 99002 참조.",  # 5자리 무관 숫자
    "참고문헌 ISBN 978-89-12345-67-8 발행.",
    # 차량번호 형태지만 hangul 코드가 아님
    "30강 123가지 사례를 검토하였다.",
    "12원 13전 시대의 화폐 단위였다.",
    # 회계·예산
    "2024 회계연도 결산 총괄 보고서 작성 중.",
    "공시이율 3.5%, 적용기간 2024-01-01 부터 2024-12-31 까지.",
    # 일반 한국어 문장 (PERSON FP 위험)
    "검토 결과 모두 적정하다고 판단되었다.",
    "성실하게 직무를 수행하였으며 안전사고는 없었다.",
    "본 안건은 관련 부서와 협의 후 처리 예정이다.",
]


def test_no_fp_in_natural_text():
    """일반 자연어에서 0건 검출되어야 한다."""
    fps_by_case: list[tuple[str, list[str]]] = []
    for text in _FP_CASES:
        detections = detect_all(text)
        if detections:
            labels = [f"{d.label}({d.text!r})" for d in detections]
            fps_by_case.append((text, labels))

    # 허용 가능한 false positive 가 0이어야 한다
    assert not fps_by_case, (
        "다음 자연어에서 false positive 발생:\n"
        + "\n".join(f"  {t!r} → {fps}" for t, fps in fps_by_case)
    )


def test_no_pii_returns_empty():
    """단순 단어들."""
    samples = [
        "안녕하세요",
        "오늘 날씨가 좋습니다.",
        "회의 잘 마쳤습니다 감사합니다.",
        "다음에 또 뵙겠습니다.",
        "수고하셨습니다.",
    ]
    for s in samples:
        results = detect_all(s)
        assert results == [], f"FP in {s!r}: {[(d.label, d.text) for d in results]}"


_CORNER_CASES: list[tuple[str, list[str]]] = [
    # (text, allowed_labels)  — 일부 자연어 + 어떤 PII 카테고리는 허용됨
    ("회사 사번 20231234 입력", ["EMPLOYEE_ID"]),
    ("문서번호: 기재부-인사-2024-12345", ["DOC_ID"]),
    ("처방번호 202412010001", ["PRESCRIPTION_ID"]),
    ("PNU: 1111011600100010000", ["PNU"]),
    # 12자리 숫자 + 키워드 없음 → 무엇도 잡으면 안 됨
    ("코드 123456789012 참조", []),
    # 16자리 random (카드 BIN/Luhn 모두 실패하면 검출 안 됨)
    ("주문번호 1111222233334444 처리 중", []),
    # 8자리 + 키워드 없음
    ("일련번호 12345678 등록", []),
    # 우편번호 같지만 prefix 미할당 (09 또는 99 시작)
    ("우편번호 09999 미할당", []),
    ("우편번호 99000 미할당", []),
]


def test_corner_cases_only_intended_labels():
    """각 케이스에서 *허용된* 라벨만 검출되고 그 외 라벨은 없어야 한다."""
    for text, allowed in _CORNER_CASES:
        results = detect_all(text)
        labels_found = {d.label for d in results}
        unwanted = labels_found - set(allowed)
        assert not unwanted, (
            f"text={text!r} : 허용 라벨 {allowed} 외 추가 검출 {unwanted} "
            f"(전체: {[(d.label, d.text) for d in results]})"
        )
