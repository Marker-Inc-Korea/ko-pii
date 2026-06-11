"""33종 PII 카테고리 정본 레지스트리 — ``include``/``exclude`` 라벨 키의 단일 진실.

- CLI: ``ko-pii --labels``
- Python: ``from ko_pii.labels import ALL_LABELS, LABEL_INFO``

한글명은 ``modes/redact.py`` 의 치환명과 동일하게 유지된다 (테스트로 동기화 보증).
"""
from __future__ import annotations

#: (한글명, 그룹, 검출 방식) — 그룹·방식은 README "33 PII 카테고리" 절과 동일 분류.
LABEL_INFO: dict[str, tuple[str, str, str]] = {
    # ── 결정적 검증 (체크섬·화이트리스트) ──
    "RRN": ("주민등록번호", "결정적 검증", "13자리+날짜+체크섬(2020+ 는 신뢰도 신호)"),
    "FRN": ("외국인등록번호", "결정적 검증", "성별자리 5-8 + 체크섬"),
    "BUSINESS_REG": ("사업자등록번호", "결정적 검증", "국세청 가중합 체크섬"),
    "CORP_REG": ("법인등록번호", "결정적 검증", "법인 체크섬 (RRN 우선)"),
    "DRIVER_LICENSE": ("운전면허번호", "결정적 검증", "지방청 코드 화이트리스트"),
    "PASSPORT": ("여권번호", "결정적 검증", "prefix(M/S/PP 등) + 8자리"),
    "CARD": ("카드번호", "결정적 검증", "BIN 화이트리스트 + Luhn"),
    "PNU": ("토지번호", "결정적 검증", "19자리 + 시·도 코드"),
    # ── 키워드 anchor (키워드 + 형식 모두 필요) ──
    "MEDICAL_INSURANCE": ("건강보험증번호", "키워드 anchor", "건강보험/보험증 키워드"),
    "PRESCRIPTION_ID": ("처방번호", "키워드 anchor", "처방/Rx/교부 키워드"),
    "EDI_DRUG": ("약품코드", "키워드 anchor", "약품코드 키워드 + GS1"),
    "FAX": ("팩스번호", "키워드 anchor", "팩스/FAX 키워드"),
    "ACCOUNT": ("계좌번호", "키워드 anchor", "계좌/은행명 60+ 키워드"),
    "EMPLOYEE_ID": ("사번", "키워드 anchor", "사번/직원번호/임용번호 키워드"),
    "PETITION_ID": ("민원번호", "키워드 anchor", "민원/청구/정보공개 키워드"),
    "COURT_CASE": ("사건번호", "키워드 anchor", "사건유형(가합/고합/헌가 등)"),
    # ── 형식 검증 ──
    "PHONE": ("전화번호", "형식 검증", "010~019/02/0NN/070/15xx/+82"),
    "EMAIL": ("이메일", "형식 검증", "RFC 5322"),
    "IP": ("IP", "형식 검증", "IPv4 옥텟 + IPv6"),
    "URL": ("URL", "형식 검증", "http(s)/ftp"),
    "POSTAL_CODE": ("우편번호", "형식 검증", "시·도 첫자리 매핑"),
    "VEHICLE": ("차량번호", "형식 검증", "NN가NNNN + 용도 한글"),
    "DOC_ID": ("문서번호", "형식 검증", "부처명 + 형식"),
    # ── 사전·컨텍스트 ──
    "PERSON": ("성명", "사전·컨텍스트", "성씨 사전 + 문맥 점수기"),
    "ADDRESS": ("주소", "사전·컨텍스트", "행정구역 + 법정동 사전"),
    "NATIONALITY": ("국적", "사전·컨텍스트", "국가명 70+"),
    "EDUCATION": ("학력", "사전·컨텍스트", "대학 ~330 + 약칭"),
    "MAJOR": ("전공", "사전·컨텍스트", "학과 ~400"),
    "POSITION": ("직책", "사전·컨텍스트", "직함 250+"),
    # ── 인적 속성 (준식별자 — 결합 시 식별 위험) ──
    "DT_BIRTH": ("생년월일", "인적 속성", "날짜 + 키워드/마커"),
    "AGE": ("나이", "인적 속성", "N세/N살/N대/개월"),
    "HEIGHT": ("신장", "인적 속성", "Ncm/N.Nm (50–250)"),
    "WEIGHT": ("체중", "인적 속성", "Nkg (1–300)"),
}

GROUPS: tuple[str, ...] = ("결정적 검증", "키워드 anchor", "형식 검증",
                           "사전·컨텍스트", "인적 속성")

ALL_LABELS: tuple[str, ...] = tuple(LABEL_INFO)


def format_labels_table() -> str:
    """``ko-pii --labels`` 출력용 그룹별 표."""
    lines = [f"ko-pii PII 카테고리 {len(ALL_LABELS)}종 — include/exclude 에 쓰는 라벨 키", ""]
    for g in GROUPS:
        items = [(k, v) for k, v in LABEL_INFO.items() if v[1] == g]
        lines.append(f"[{g}] ({len(items)})")
        w = max(len(k) for k, _ in items)
        for k, (ko, _, how) in items:
            lines.append(f"  {k:<{w}}  {ko:　<8}  {how}")
        lines.append("")
    lines.append('사용 예: ko-pii doc.txt --include RRN,PHONE / detect_all(text, exclude=["PERSON"])')
    return "\n".join(lines)
