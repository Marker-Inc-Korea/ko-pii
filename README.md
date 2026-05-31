# ko-pii

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Demo](https://img.shields.io/badge/demo-HuggingFace-yellow.svg)](https://huggingface.co/spaces/modak000/ko-pii-demo)

**한국어 문서의 개인정보를 검출하고 가역적으로 가명화하는 Python 라이브러리.** 외부 ML 의존성 없이 룰 + 사전 + 체크섬만으로 동작. 공공 문서에서 특히 강하며, 어떤 ML 파이프라인의 전처리 레이어로도 활용 가능.

```python
from ko_pii import Anonymizer, ProcessingMode

result = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize").process(
    "신청인 홍길동 (880101-1234568) 연락처 010-1234-5678"
)
print(result.text)
# 신청인 <PERSON_1> (<RRN_1>) 연락처 <PHONE_1>

print(result.vault.reveal("<RRN_1>"))            # 880101-1234568 (권한자만 복원)
print(result.combined_risk.combined_risk)        # RiskLevel.CRITICAL
```

### 가명화 전후 비교

```
원본:
  신청인 홍길동 (880101-1234568) 연락처 010-1234-5678
  주소: 서울특별시 강남구 테헤란로 152

tokenize (토큰 치환 + Vault 복원 가능):
  신청인 <PERSON_1> (<RRN_1>) 연락처 <PHONE_1>
  주소: <ADDRESS_1>

partial (일부만 가림 — 실무 양식):
  신청인 홍** (880101-1******) 연락처 010-****-5678
  주소: 서울특별시 강남구 ***

redact (카테고리명 치환):
  신청인 [성명] ([주민등록번호]) 연락처 [전화번호]
  주소: [주소]
```

> **처음이시면:** `mode=ProcessingMode.STRICT` + `strategy="tokenize"` 추천. 가장 안전한 기본 설정 (MEDIUM 위험도 이상 차단 + Vault 복원 가능).

### 이런 것도 됩니다

- **조사 붙어있어도 잡힘** — "홍길동이" "홍길동에게" "홍길동의" → 조사 자동 분리 후 PERSON 검출
- **한자 병기** — "홍길동(洪吉童)" → 한글+한자 모두 인식
- **로마자 이름** — "Hong Gildong" → 한글로 정규화 후 매칭
- **HWP/HWPX/DOCX/PDF 직접 입력** — `ko-pii report.hwp --strategy tokenize` (표·머리말·꼬리말·메타데이터 모두 처리)
- **CSV/XLSX 헤더 자동 인식** — "성명/주민번호/연락처" 헤더 → 자동으로 PERSON/RRN/PHONE 매핑
- **공문서 날짜 자동 거부** — "시행일자: 2026-05-21" "감사기간: 3월~4월" → 생일 아님 (비-생일 키워드 30+)
- **가명 표기 자동 거부** — "박씨" "김모씨" "○○○ 시민" → 이미 가명화됨 (PII 아님)
- **결합 위험도 자동 평가** — 이름만으로는 PII 아닐 수 있지만, *이름 + 주민번호 + 주소* 가 같이 나오면 → CRITICAL (「개인정보 비식별 조치 가이드라인」 의 준식별자 결합 검증)
- **감사 로그** — 누가·언제·어떤 토큰을 복원했는지 JSONL 추적 (개인정보보호법 제29조)

---

## 목차

1. [주요 특징](#주요-특징)
2. [설치](#설치)
3. [사용 시나리오](#사용-시나리오)
4. [평가 결과](#평가-결과)
5. [사용법](#사용법)
6. [33 PII 카테고리](#33-pii-카테고리)
7. [검출 정책 — 어떤 접두어·anchor 가 작동하는가](#검출-정책--어떤-접두어anchor-가-작동하는가)
8. [처리 모드 + 치환 전략](#처리-모드--치환-전략)
9. [부가 기능](#부가-기능)
10. [FAQ](#faq)
11. [개발](#개발)
12. [라이선스](#라이선스)

---

## 주요 특징

- **한국 특화** — 한국어 PII 33 카테고리 (RRN · FRN · 여권 · 사업자 · 카드 · 계좌 · 전화 · 이메일 · 주소 · 차량 · 인명 · 직책 · 국적 등). 공공 문서에서 특히 강함
- **결정적 검출** — 룰 + 사전 + 체크섬. 주민등록번호·카드·사업자번호 등은 체크섬 검증으로 F1 ≈ 1.000
- **우회 차단** — 전각 숫자(`０１０`)·제로폭 문자 삽입 등 유니코드 우회를 정규화로 무력화 (검출 offset 은 원본 보존)
- **외부 의존성 없음** — Python 표준 라이브러리만 사용. 오프라인/폐쇄망 동작, GPU 불필요
- **전처리 레이어** — `DetectionResult` (label/start/end/text/confidence) 표준 객체 출력. ML 파이프라인 앞단에 끼워넣기 편함
- **가역 가명화 + Vault** — 토큰 ↔ 원본 매핑을 별도 저장소에 분리, 복원 가능
- **법적 근거 자동 부착** — 각 검출에 개인정보보호법 조항 자동 부착 (감사 추적)
- **다양한 입력** — TXT · CSV · XLSX · HWP · HWPX · DOCX · PDF (`[file]` extras)

### 도메인별 활용 가이드

| 도메인 | 권장 설정 | 비고 |
|---|---|---|
| 공공 문서 (공문서·민원·인사) | `STRICT` + `tokenize` | 기본값. 가장 잘 맞는 도메인 |
| LLM 학습 데이터 전처리 | `PARANOID` + `tokenize` 또는 `redact` | 누수 차단 우선 |
| 의약품·바이오 | `STRICT` + `exclude={"AGE","HEIGHT","WEIGHT"}` | "체중 1kg당" 같은 용법 오탐 방지 |
| 금융·보험 | `STRICT` + `tokenize` | RRN·카드·계좌 결정적 검출 |
| 일반 사무 (사내 문서) | `BALANCED` + `partial` | 읽기 편한 부분 마스킹 |

```python
# 의약품 도메인 — PERSON FP 방지 + 신체속성 오탐 방지
anon = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    exclude={"AGE", "HEIGHT", "WEIGHT"},  # "체중 1kg당" 오탐 방지
)

# PERSON FP 가 많다면 — 도메인 사전 주입
# src/ko_pii/dictionaries/common_words.py 에 의약품 성분명·제조사명 추가
# 예: "이부프로펜", "한미약품", "메트포르민" → PERSON 에서 자동 제외
```

---

## 설치

```bash
pip install ko-pii
```

extras 옵션 (필요 시):

```bash
pip install "ko-pii[file]"       # HWP/HWPX/DOCX/PDF
pip install "ko-pii[security]"   # Vault AES-256-GCM
```

**Python 3.10 이상.** 코어는 표준 라이브러리만 사용.

---

## 사용 시나리오

### 시나리오 1 — 결재 공문 일괄 가명화 (외부 공개·LLM 전송 전)

```python
from pathlib import Path
from ko_pii import Anonymizer, ProcessingMode

anon = Anonymizer(mode=ProcessingMode.PARANOID, strategy="tokenize")

for path in Path("./공문서/").glob("*.hwp"):
    result = anon.process(path.read_text(encoding="utf-8"))
    Path(f"./가명화/{path.name}").write_text(result.text, encoding="utf-8")
    # vault.json 분리 보관 (권한 있는 사용자만 복원 가능)
    result.vault.save(f"./vault/{path.stem}.json")
```

- **PARANOID 모드** — LOW 위험도 이상 모두 차단 (LLM/외부 전송 안전)
- 가명화 결과는 외부에, Vault 는 사내 저장소에 분리 보관
- HWP/HWPX 파서: `pip install "ko-pii[file]"`

### 시나리오 2 — 민원 응대 시스템에서 사전 PII 검증

```python
from ko_pii import Anonymizer, ProcessingMode, RiskLevel

anon = Anonymizer(mode=ProcessingMode.AUDIT)  # 차단 X, 검출만 보고

result = anon.process(incoming_petition_text)

# 결합 위험도가 CRITICAL 이면 담당자에게 알림
if result.combined_risk.combined_risk >= RiskLevel.CRITICAL:
    notify_admin(
        identifiers=result.combined_risk.identifiers,        # {"RRN", "PHONE"}
        quasi=result.combined_risk.quasi_identifiers,        # {"PERSON", "ADDRESS"}
    )

# 응대 직원에게는 가명화 버전 제공
masked = Anonymizer(mode=ProcessingMode.STRICT, strategy="partial").process(
    incoming_petition_text
).text
```

- **AUDIT 모드** — 차단 없이 검출만 보고 (감사·통계용)
- **결합 위험도** 자동 평가 — 「개인정보 비식별 조치 가이드라인」 의 준식별자 결합 검증
- 응대 직원에게는 `partial` 전략으로 일부만 마스킹 (`880101-1******`)

### 시나리오 3 — Python 로그에 PII 자동 가명화 (개발자용)

```python
# 코드 어디서든 logger.info("...") 호출 시 자동 가명화
import logging
from ko_pii import Anonymizer, ProcessingMode

_anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact")

class PIIFilter(logging.Filter):
    def filter(self, record):
        record.msg = _anon.process(str(record.msg)).text
        return True

logging.getLogger().addFilter(PIIFilter())
logging.info("신청인 홍길동 (880101-1234568) 처리 완료")
# → "신청인 [성명] ([주민등록번호]) 처리 완료"
```

---

## 평가 결과

| 평가 도메인 | 문서 수 | ko-pii | openai/PF | Presidio |
|---|---:|---:|---:|---:|
| **행정문서 + PII 주입 (메인)** | 200 | **0.901** | 0.480 | 0.455 |
| LLM 생성 벤치마크 | 187 | **0.770** | 0.434 | 0.446 |
| KDPII (한국어 일상 대화) | 4,891 | **0.656** | 0.382 | 0.367 |
| KLUE-NER (신문기사 풀네임) | 5,000 | **0.419** | 0.155 | 0.000 |

모든 벤치마크에서 [openai/privacy-filter](https://huggingface.co/openai/privacy-filter) (660M 다국어 ML 모델) 와 [Microsoft Presidio](https://github.com/microsoft/presidio) (가장 인기 OSS PII 프레임워크) 대비 우위.
결정적 PII (RRN·PHONE·EMAIL·카드·사업자) 는 체크섬 검증이라 F1 ≈ 1.000.
상세 비교는 [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md) 참조.

> **운영 전 권장:** 사용하시는 도메인의 실제 문서 30~100건을 직접 테스트해보세요. 도메인마다 성능 차이가 있습니다.

### 알려진 한계

- **PERSON 오탐 (FP)** — 룰 기반 PERSON 검출의 가장 큰 약점. 도메인 어휘 (의약품 성분명 등) 가 사람 이름으로 잡힐 수 있음. → `common_words.py` 에 도메인 사전 주입 또는 `exclude={"PERSON"}` 으로 끄기
- **ADDRESS 비정형** — "강남 쪽에 살아" 같은 비정형 주소는 약함 (anchor 필요). 정형 주소 ("서울특별시 강남구 테헤란로 152") 는 OK
- 결정적 PII (RRN·PHONE·EMAIL·카드·사업자) 는 체크섬/형식 검증이라 오탐 거의 없음

상세 평가: [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md).

---

## 사용법

### CLI

```bash
# 기본
ko-pii input.txt --mode STRICT --strategy tokenize \
       --vault vault.json -o output.txt --report report.html

# 배치 (디렉토리 일괄, 병렬)
ko-pii ./incoming/ --batch --workers 4 --output-dir ./anonymized/

# Vault 암호화 + 감사 로그
KPII_VAULT_PASSWORD=secret ko-pii doc.hwp \
    --vault vault.kvault --audit-log audit.jsonl
```

### Python API

```python
from ko_pii import Anonymizer, ProcessingMode

anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
result = anon.process(text)

print(result.text)                       # 가명화된 텍스트
print(result.vault.reveal("<RRN_1>"))    # 원본 복원 (권한자만)
print(result.summary["by_label"])        # {"RRN": 1, "PHONE": 1, "PERSON": 1}
```

### 결합 위험도 + k-익명성

```python
# 검출 결과의 결합 위험도 자동 평가
print(result.combined_risk.combined_risk)        # RiskLevel.CRITICAL
print(result.combined_risk.identifiers)          # {"RRN"}
print(result.combined_risk.quasi_identifiers)    # {"PERSON", "ADDRESS", "DT_BIRTH"}

# k-익명성 평가 (집단 데이터)
from ko_pii.analytics import k_anonymity
report = k_anonymity(records, quasi_identifiers=["age", "city", "job"], k=5)
print(report.satisfies_k)                  # True/False
print(report.generalization_suggestions)   # ["age: 30-39", ...]
```

### CSV/XLSX 표 자동 처리

```python
from ko_pii.tabular import anonymize_records
import csv

rows = list(csv.DictReader(open("employees.csv")))
# 헤더 "성명/주민번호/연락처/주소" → 자동으로 PERSON/RRN/PHONE/ADDRESS 매핑
result = anonymize_records(rows, strategy="tokenize")
print(result.rows[0])
```

### 검토 큐 워크플로우 (오탐 학습)

confidence 낮은 검출 → 검토 큐에 저장 → 사용자가 FP/OK/FN 마킹 → 누적 마킹에서 사전 추천 패치 자동 생성 (자동 반영 X, 사람 검토 후 반영).

```python
result = anon.process(text)

# 1. confidence 낮아 REVIEW 분류된 검출 (모드별 자동 분류)
for record in result.review_items():
    d = record.detection
    print(d.text, d.confidence, d.evidence)

# 2. 별도 JSONL 큐에 저장 → 사용자가 verdict 마킹
from ko_pii.review.queue import ReviewQueue
q = ReviewQueue("review.jsonl")
q.enqueue_review_records(result.review_items(), document=text)

# 3. 누적 마킹 → 패치 파일 생성 (common_words 후보 / 이름 후보)
from ko_pii.review.feedback import apply_feedback
apply_feedback(
    queue_path="review.jsonl",
    output_dir="feedback_patches/",
    min_repeat=2,   # 같은 토큰이 2회 이상 FP → 후보 (사전 오염 방지)
)
# → feedback_patches/common_words_additions.txt  (PERSON FP 후보)
# → feedback_patches/names_to_add.txt           (FN 표시 이름)
# → feedback_patches/summary.json
```

### 개별 검출기 호출

```python
from ko_pii.patterns.rrn import detect

for r in detect("신청인 880101-1234568"):
    print(r.label, r.text, r.confidence, r.legal_basis)
# RRN 880101-1234568 1.0 개인정보보호법 제24조의2
```

---

## 33 PII 카테고리

### 결정적 검증 (체크섬·화이트리스트)

| 카테고리 | 검증 | 위험도 |
|---|---|---|
| RRN (주민등록번호) | 13자리 + 날짜 + 한국 체크섬 | CRITICAL |
| FRN (외국인등록번호) | gender 5-8 + 체크섬 | CRITICAL |
| 사업자등록번호 | 국세청 가중합 체크섬 | LOW |
| 법인등록번호 | 법인 체크섬 (RRN 우선) | MEDIUM |
| 운전면허번호 | 지방청 코드 11-28 화이트리스트 | HIGH |
| 여권번호 | prefix (M/S/PP/PD 등) + 8자리 | CRITICAL |
| 신용카드 | BIN 화이트리스트 + Luhn | CRITICAL |
| 필지고유번호 (PNU) | 19자리 + 시·도 코드 | LOW |

### 키워드 anchor (키워드 + 형식 모두 필요)

| 카테고리 | 키워드 |
|---|---|
| 건강보험증 | 건강보험 / 의료보험 / 보험증 |
| 처방번호 | 처방번호 / Rx / 교부번호 |
| 의약품 코드 | 약품코드 / KD코드 + 한국 GS1 |
| 팩스번호 | 팩스 / FAX |
| 계좌번호 | 계좌 / 은행명 60+ (3-way anchor) |
| 사번 | 사번 / 공무원번호 / 직원번호 / 임용번호 |
| 민원번호 | 민원 / 청구 / 정보공개 / 행정심판 |
| 사건번호 | 사건유형 (가합/고합/구합/헌가 등) |

### 형식 검증

| 카테고리 | 검증 |
|---|---|
| 전화번호 | 모바일 010-019 / 서울 02 / 지방 031-064 / VoIP 070 / 대표 15xx-18xx / +82 국제 |
| 이메일 | RFC 5322 |
| IP | IPv4 옥텟 + IPv6 RFC 4291 |
| URL | http(s) / ftp |
| 우편번호 | 시·도 첫자리 매핑 |
| 차량번호 | 신형 NN[가-힣]NNNN + 용도 한글 화이트리스트 |
| 공문서번호 | 부처명 + 형식 |

### 사전·휴리스틱

| 카테고리 | 사전 규모 |
|---|---|
| 인명 (PERSON) | 성씨 286 + 직책 인접 + 17 거부 룰 |
| 주소 (ADDRESS) | 광역 17 + 기초 226 + 빈출 동 150 + 건물 접미사 38 + 건물명 가제티어 |
| 국적 (NATIONALITY) | 국가명 70+ (대한민국·미국·일본 등) |
| 학력 (EDUCATION) | 대학 ~330 + 약칭 |
| 전공 (MAJOR) | 학과 ~400 (KEDI 분류) |
| 직책 (POSITION) | titles 250+ (정부·경찰·소방·군·검사·법관·민간) |

### 인적 속성 (준식별자 — 결합 시 식별 위험)

| 카테고리 | 검증 | 위험도 |
|---|---|---|
| 생년월일 | 날짜 + 키워드/풀네임/년생 marker | HIGH |
| 나이 | "32세 / 32살 / 환갑 / 12개월 아기 / 30대" | INFO |
| 신장 | "175cm / 1.75m" 50–250 | INFO |
| 체중 | "70kg / 70킬로" 1–300 | INFO |

> **준식별자 (Quasi-Identifier)** 단독으로는 식별 불가지만 다른 정보와 결합 시 재식별 위험. `analytics/combined_risk` 가 자동 평가.

---

## 검출 정책 — 어떤 접두어·anchor 가 작동하는가

각 PII 검출은 *단순 정규식 매칭이 아닌 multi-gate*: **접두어 라벨 / 키워드 anchor / 문맥 사전 / 형식 검증** 의 조합.

### PERSON 필드 라벨 (50+ 항목)

라벨 직후 1~4글자 한글 → 강한 PERSON 후보.

| 도메인 | 라벨 |
|---|---|
| 기본 | `성명` `이름` `성함` `이 름` |
| 민원·행정 | `신청인` `신청자` `민원인` `청구인` `보호자` `대리인` `당사자` |
| 결재 | `기안자` `결재자` `검토자` `보고자` `수신자` `발신자` `참조` |
| 사법 | `원고` `피고` `고소인` `피고소인` `증인` `감정인` |
| 경찰·소방 | `피의자` `피해자` `용의자` `참고인` `신고자` `수사관` `출동대장` |
| 인사 | `평가자` `피평가자` `면담자` `추천인` |
| 의료 | `환자` |

라벨 variant 7종 인식: `성명: 홍길동` / `[성명] 홍길동` / `(성명) 홍길동` / `<성명> 홍길동` 등.

### PERSON 거부 룰 (17+, FP 방지)

- **단성 + 직급/지역/학교/은행**: `김부장` `김포시` `이화여대` → 거부
- **한국어 어말 형태소 16종**: `~은데` `~는데` `~라서` `~까지` 끝 → 거부
- **부처·기관명**: `보건복지부` `행정안전부` → 거부
- **이미 가명화된 표기**: `박씨` `김모씨` `○○○ 시민` → 거부

### 검출 예시

```
✓ 성명: 김도윤               (필드 라벨)
✓ 박지훈 과장님께            (직책 인접)
✓ 홍길동(洪吉童)             (한자 병기)
✓ 880101-1234568            (RRN — 체크섬)
✓ 120-81-47521              (사업자 — 국세청 체크섬)
✓ 4242-4242-4242-4242       (카드 — Luhn)
✓ M12345678                 (여권)

✗ 김부장이 협조 안 함        (호칭 = 거부)
✗ 보건복지부는 검토 후        (부처명)
✗ 시행일자: 2026-05-20       (비-생일 거부)
✗ 881301-1000004            (RRN — 13월 무효)
✗ A12345678                 (여권 — A prefix 거부)
```

---

## 처리 모드 + 치환 전략

| 모드 | 차단 기준 | 용도 |
|---|---|---|
| `PARANOID` | LOW 이상 모두 차단 | 외부 공개·LLM 전송 전 |
| `STRICT` | MEDIUM 이상 차단 | 실무 표준 (기본값) |
| `BALANCED` | HIGH 이상 차단 | 내부 협업 |
| `PERMISSIVE` | CRITICAL 만 차단 | 분석가 작업 |
| `AUDIT` | 차단 없음, 검출만 보고 | 감사·통계 |

| 전략 | `880101-1234568` → | 가역 | 설명 |
|---|---|:-:|---|
| `tokenize` | `<RRN_1>` | ✓ | 토큰 치환, Vault 에 원본 보관 |
| `redact` | `[주민등록번호]` | ✗ | 카테고리명으로 치환 |
| `partial` | `880101-1******` | ✗ | 일부만 가림 (실무 표준) |
| `asterisk` | `**************` | ✗ | 별표 마스킹 |
| `hashed` | `<RRN:abc123>` | ✗ | 해시 (같은 값 → 같은 토큰) |
| `fpe` | `771202-2345671` | ✗ | 형식 유지 암호화 (FPE) |

---

## 부가 기능

| 기능 | 설명 | 설치 |
|---|---|:---:|
| **HWP/HWPX/DOCX/PDF 파서** | 한컴오피스·MS Word·PDF 자동 파싱 (본문 + 표 + 머리말 + 메타데이터). 아래 파서 상세 참고 | `[file]` |
| **Vault 암호화** | AES-256-GCM + PBKDF2 480k 반복 | `[security]` |
| **감사 로그 (JSONL)** | 모든 `reveal()` 호출 기록 (개인정보보호법 제29조) | 코어 |
| **배치 처리** | 디렉토리 일괄 + 병렬 워커 | 코어 |
| **검토 큐** | confidence 낮은 검출 → 사람 검토 → 오탐 어휘 자동 학습 | 코어 |
| **HTML 리포트** | 정탐 초록 / 오탐 빨강 / 미탐 노랑 시각화 | 코어 |
| **한자/로마자 변형** | `洪吉童` → `홍길동`, `Hong Gildong` → `홍길동` | 코어 |

### 파서 상세

| 포맷 | 사용 라이브러리 | 비고 |
|---|---|---|
| HWP 5.x | [olefile](https://pypi.org/project/olefile/) | OLE 바이너리 레코드 직접 파싱, 본문 텍스트 추출 |
| HWPX | stdlib (`zipfile` + `xml`) | ZIP+XML 구조, 외부 의존성 없음 |
| DOCX | stdlib (`zipfile` + `xml`) | ZIP+XML 구조, 외부 의존성 없음 |
| XLSX | stdlib (`zipfile` + `xml`) | sharedStrings + sheet XML |
| PDF | [pdfplumber](https://pypi.org/project/pdfplumber/) (우선) / [pypdf](https://pypi.org/project/pypdf/) (fallback) | 텍스트 레이어만 추출 (스캔 PDF는 OCR 필요) |

> **PDF 참고:** PDF는 글자 좌표 기반이라 칸별 공백·줄바꿈 삽입이 흔합니다. ko-pii는 내장 정규화 엔진(`text_normalizer`)으로 PII 패턴 중간의 불필요 공백/줄바꿈을 자동 보정합니다. pdfplumber가 pypdf보다 레이아웃 분석이 우수하므로 pdfplumber 설치를 권장합니다.

---

## FAQ

**Q1. ML 없이 룰만으로 정말 잘 되나요?**
한국 핵심 PII (주민번호·여권·카드·사업자 등) 는 체크섬 검증으로 F1 ≈ 1.000 — ML 로 대체 불가능한 영역. PERSON 같은 맥락 의존적 PII 는 ML 이 더 나을 수 있지만, 공공 문서에서는 F1 0.795 로 실용적.

**Q2. 오탐이 많으면?**
`common_words.py` 에 도메인 사전 주입, `exclude={"PERSON"}` 으로 특정 카테고리 끄기, 모드 변경 (`STRICT` → `BALANCED`).

**Q3. Vault 분실하면?**
복원 불가 (보안 설계). `[security]` extras 로 암호화 보관 또는 `strategy="redact"` (카테고리명 치환, Vault 불필요) 사용.

**Q4. HWP 표·머리말 다 잡히나요?**
네. `[file]` extras 설치 시 본문 + 표 + 머리말 + 꼬리말 + 메타데이터 모두 추출.

**Q5. 다른 도구 (Presidio / openai) 와 뭐가 다르나요?**
- **Presidio** — 영어 위주. 한국 특화 PII (RRN/FRN/여권 등) 부재
- **openai/privacy-filter** — 다국어 일반 PII. 한국 핵심 14 카테고리 라벨 없음
- **ko-pii** — 한국 특화 33 카테고리, 체크섬 검증, 법적 근거 자동 부착

**Q6. 이름 단독 검출이 오탐이 많아요. 이름+전화번호 같이 있을 때만 차단할 수 있나요?**
`PERMISSIVE` 모드 (CRITICAL만 차단) + `combined_risk` 조건부 재처리:
```python
result = Anonymizer(mode=ProcessingMode.PERMISSIVE).process(text)
if result.combined_risk.combined_risk >= RiskLevel.HIGH:
    result = Anonymizer(mode=ProcessingMode.STRICT).process(text)
```

---

## 개발

```bash
git clone https://github.com/modak000/ko-pii
cd ko-pii
pip install -e ".[dev]"
pytest    # 699 passed
```

상세 문서: [`docs/`](docs/) 디렉토리 참조.

---

## 라이선스

Apache License 2.0

## 법령 참고

- 개인정보보호법 (제2조, 제23조, 제24조, 제24조의2, 제28조의2-5, 제29조)
- 개인정보보호위원회 「가명정보 처리 가이드라인」 · 「개인정보 비식별 조치 가이드라인」
- 상법 제40조 · 출입국관리법 제31조 · 국민건강보험법 제96조 · 금융실명법
