# Microsoft Presidio Plugin

[Microsoft Presidio](https://github.com/microsoft/presidio) 는 가장 인기 있는
OSS PII 검출·가명화 프레임워크. ko-pii 의 한국 공공 도메인 fit 을 Presidio
사용자가 *한 줄로* 활용할 수 있게 하는 plugin.

## 설치

```bash
pip install ko-pii[presidio]
# 또는
pip install ko-pii presidio-analyzer presidio-anonymizer
```

## 사용

```python
from presidio_analyzer import AnalyzerEngine
from ko_pii.integrations.presidio_plugin import KPiiRecognizer

# 1) Presidio Analyzer 초기화
analyzer = AnalyzerEngine()

# 2) ko-pii recognizer 등록
analyzer.registry.add_recognizer(KPiiRecognizer())

# 3) 한국 PII 인식
text = "홍길동(880101-1234568)의 연락처: 010-1234-5678"
results = analyzer.analyze(text=text, language="ko")

for r in results:
    print(f"{r.entity_type}: {text[r.start:r.end]} (score {r.score})")
# 출력:
#   PERSON: 홍길동 (score 0.65)
#   KR_RRN: 880101-1234568 (score 1.0)
#   PHONE_NUMBER: 010-1234-5678 (score 1.0)
```

## Presidio 사용자가 얻는 것

| 기능 | Presidio 기본 | + ko-pii plugin |
|---|---|---|
| RRN (주민등록번호) 검출 + 체크섬 | ❌ | ✅ KR_RRN |
| 사업자등록번호 + 국세청 체크섬 | ❌ | ✅ KR_BUSINESS_REG |
| 법인등록번호 + 체크섬 | ❌ | ✅ KR_CORP_REG |
| 한국 운전면허번호 | ❌ | ✅ KR_DRIVER_LICENSE |
| 한국 휴대전화 (010~019) | ⚠️ 부분적 | ✅ PHONE_NUMBER |
| 의료보험증번호 (건강·민감) | ❌ | ✅ KR_MEDICAL_INSURANCE |
| 한국 차량번호 (가나다 등) | ❌ | ✅ KR_VEHICLE_PLATE |
| 한국 도로명/지번 주소 | ❌ | ✅ KR_ADDRESS |
| 우편번호 (5자리·6자리) | ❌ | ✅ KR_POSTAL_CODE |
| 처방번호·KCD 진단코드 | ❌ | ✅ KR_PRESCRIPTION_ID / KR_KCD |
| 법원 사건번호 | ❌ | ✅ KR_COURT_CASE |
| 한국 성명 (컨텍스트 기반) | ⚠️ 약함 | ✅ PERSON |

총 **22개 한국 특화 / 표준 라벨** 추가.

## 라벨 매핑 표

| ko-pii 라벨 | Presidio 라벨 |
|---|---|
| RRN | `KR_RRN` |
| FRN | `KR_FRN` |
| BUSINESS_REG | `KR_BUSINESS_REG` |
| CORP_REG | `KR_CORP_REG` |
| DRIVER_LICENSE | `KR_DRIVER_LICENSE` |
| MEDICAL_INSURANCE | `KR_MEDICAL_INSURANCE` |
| PRESCRIPTION_ID | `KR_PRESCRIPTION_ID` |
| KCD | `KR_KCD` |
| EDI_DRUG | `KR_EDI_DRUG` |
| VEHICLE | `KR_VEHICLE_PLATE` |
| POSTAL_CODE | `KR_POSTAL_CODE` |
| ADDRESS | `KR_ADDRESS` |
| ACCOUNT | `KR_BANK_ACCOUNT` |
| EMPLOYEE_ID | `KR_EMPLOYEE_ID` |
| DOC_ID | `KR_DOC_ID` |
| PETITION_ID | `KR_PETITION_ID` |
| COURT_CASE | `KR_COURT_CASE` |
| PNU | `KR_LAND_ID` |
| PASSPORT | `US_PASSPORT` (Presidio 표준) |
| CARD | `CREDIT_CARD` |
| PHONE | `PHONE_NUMBER` |
| FAX | `PHONE_NUMBER` |
| EMAIL | `EMAIL_ADDRESS` |
| IP | `IP_ADDRESS` |
| URL | `URL` |
| PERSON | `PERSON` |

## 메타데이터

각 `RecognizerResult` 의 `recognition_metadata` 에 ko-pii 의 원본 정보 보존:

```python
result = results[0]
result.recognition_metadata["ko_pii_label"]        # 'RRN'
result.recognition_metadata["ko_pii_risk_level"]   # 'CRITICAL'
result.recognition_metadata["ko_pii_legal_basis"]  # '개인정보보호법 제24조의2'
result.recognition_metadata["ko_pii_evidence"]     # ['pattern:rrn', 'checksum:valid', ...]
```

→ Presidio 사용자가 한국 *법적 근거* 까지 얻음. 감사 추적 용이.

## Presidio Anonymizer 와 결합

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from ko_pii.integrations.presidio_plugin import KPiiRecognizer

analyzer = AnalyzerEngine()
analyzer.registry.add_recognizer(KPiiRecognizer())

anonymizer = AnonymizerEngine()

text = "홍길동 880101-1234568"
results = analyzer.analyze(text=text, language="ko")
anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
print(anonymized.text)
# → <PERSON> <KR_RRN>
```

## 필터링

특정 카테고리만 사용:

```python
# 한국 RRN 과 전화번호만
recognizer = KPiiRecognizer(include=["RRN", "PHONE"])
analyzer.registry.add_recognizer(recognizer)
```

또는 Presidio API 로 호출 시 entity 지정:

```python
results = analyzer.analyze(
    text=text, language="ko",
    entities=["KR_RRN", "PHONE_NUMBER"],
)
```

## 주의

- ko-pii recognizer 는 `language="ko"` 에서만 활성. 영어 텍스트에는 Presidio
  기본 recognizer 사용.
- nlp_engine (spaCy 등) 은 *필요 없음* — ko-pii 는 자체 룰 기반.
- Presidio 의 score 임계값 (`AnalyzerEngine.analyze(score_threshold=...)`)
  과 호환.
