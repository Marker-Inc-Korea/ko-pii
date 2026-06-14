"""ko-pii 블루팀(정상 → 과탐/FPR) + 레드팀(합성 PII → 탐지/recall) 평가.

    PYTHONPATH=src python eval/blueteam.py

블루팀: 식약처 도메인 문서·일상 텍스트(생약명/제품코드/날짜/버전/섹션/loopback 등).
모두 미검출이어야 한다 → 과탐(FPR) 측정. 레드팀: 합성 PII(주민/외국인/카드/전화/
계좌/사업자 + 난독). 모두 검출이어야 한다 → 탐지(recall) 측정. 합성 PII 만 사용.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ko_pii import detect_all  # noqa: E402

# 블루팀 — 비-PII 정상 텍스트(식약처 도메인 대량). 검출되면 과탐.
BENIGN: list[str] = [
    # 생약명/한약재 처방 (성씨 글자 시작 → PERSON 오탐 위험)
    "황기와 인삼을 배합한 처방입니다.",
    "당귀, 천궁, 작약을 군약으로 한다.",
    "산수유 오미자 갈근을 달여 복용한다.",
    "시호와 황금으로 구성된 한방 제제.",
    "백출 복령 진피 반하를 배합한다.",
    "방풍 형개 강활 독활 처방",
    "녹용 홍삼 부자 계피 보양제",
    "황련 황백 대황 치자 청열제",
    "택사 저령 활석 이수제",
    "원지 용골 모려 안신제",
    "후박 목향 오약 길경 이기제",
    "익모초 차전자 도라지 강황 추출물",
    # 성분/부형제
    "주성분 도파민, 부형제 유당 전분",
    "마그네슘 구연산 사카린 함유",
    "유산균 비피더스 제아잔틴 판테놀 배합",
    "아르기닌 아스파탐 함유 음료",
    "도부타민 도세탁셀 유데나필 성분",
    # MFDS 카테고리/행정
    "수입식품 의약외품 마약류 품목 분류 안내",
    "화장품 위생용품 임상시험 관리",
    "수입신고 제조판매 허가 절차",
    "품목허가번호 제2023-0034호 제품 정보",
    "건강기능식품 기능성 원료 목록",
    # 제품 라벨/코드/번호
    "제조번호 LOT240315, 사용기한 2025.12.31",
    "바코드 8801234567890 재고 확인",
    "도서 ISBN 9788956609959 절판",
    "허가번호 202300123456789012 조회",
    "로트번호 ABCD1234EFGH5678 회수 대상",
    "단말기 IMEI 353280112345674 분실 신고",
    "운송장 1Z999AA10123456784 조회",
    # 날짜/버전/섹션
    "소프트웨어 버전 10.0.19.41 배포",
    "v1.2.3.4 릴리스 노트 확인",
    "Section 4.2.1.3 of the manual",
    "표 3.2.1.4 항목 참조",
    "회의는 2024-03-15 오후 3시",
    "유통기한 2026.06.30 까지",
    # 인프라(loopback/예약 IP)
    "테스트 로그: 127.0.0.1 에 기록됨",
    "게이트웨이 0.0.0.0 설정",
    "브로드캐스트 255.255.255.255 주소",
    # 일반/분수
    "오늘 회의 자료를 정리했습니다.",
    "다음 주 화요일에 보고드리겠습니다.",
    "½컵 설탕과 ⅓컵 소금을 넣으세요.",
]

# 레드팀 — 합성 PII(검출 기대). (라벨, 텍스트)
PII: list[tuple[str, str]] = [
    ("RRN", "주민등록번호 900101-2345678"),
    ("RRN", "제 번호는 900101-1234567 입니다"),
    ("RRN-obf", "주민 ٩٠٠١٠١-١٢٣٤٥٦٧"),                 # Arabic-Indic
    ("RRN-obf", "주민등록번호 9001ᄀ01-1234567"),          # conjoining jamo
    ("RRN-obf", "주민 900101⁄5234567"),                  # fraction slash
    ("FRN", "외국인등록번호 900101-5234569"),
    ("FRN", "외국인등록번호 900101.5234569"),
    ("CARD", "카드 4111-1111-1111-1111"),
    ("CARD-obf", "카드번호 ❹❶❶❶-❶❶❶❶-❶❶❶❶-❶❶❶❶"),       # circled digits
    ("PHONE", "연락처 010-1234-5678"),
    ("PHONE", "고객센터 1588-1234 로 문의"),
    ("PHONE-obf", "연락처 010·1234·5678"),               # middle-dot
    ("ACCOUNT", "신한은행 110-456-789012 로 입금"),
    ("BIZNO", "사업자등록번호 220-81-62517"),
    ("EMAIL", "이메일 hong@example.com 으로 연락"),
    ("PERSON", "담당자 김철수 사무관입니다"),
]


def main() -> None:
    fp = [t for t in BENIGN if detect_all(t)]
    tn = len(BENIGN) - len(fp)
    tp = [(lbl, t) for lbl, t in PII if detect_all(t)]
    fn = [(lbl, t) for lbl, t in PII if not detect_all(t)]

    n_fp, n_tp, n_fn = len(fp), len(tp), len(fn)
    fpr = n_fp / len(BENIGN) if BENIGN else 0.0
    recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else 0.0
    precision = n_tp / (n_tp + n_fp) if (n_tp + n_fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print("=" * 64)
    print(f"블루팀 — 정상 텍스트 {len(BENIGN)}개 (과탐 측정)")
    print(f"  통과(TN) {tn}/{len(BENIGN)}   과탐(FP) {n_fp}/{len(BENIGN)}   FPR {fpr:.1%}")
    for t in fp:
        print(f"    ✗ FP  {t[:50]}  →  {[(d.label, d.text) for d in detect_all(t)]}")
    print("=" * 64)
    print(f"레드팀 — 합성 PII {len(PII)}개 (탐지 측정)")
    print(f"  검출(TP) {n_tp}/{len(PII)}   누락(FN) {n_fn}/{len(PII)}   Recall {recall:.1%}")
    for lbl, t in fn:
        print(f"    ✗ MISS [{lbl}] {t[:50]}")
    print("=" * 64)
    print(f"종합  Precision {precision:.3f}  Recall {recall:.3f}  F1 {f1:.3f}  FPR {fpr:.1%}")
    print("=" * 64)


if __name__ == "__main__":
    main()
