# Microsoft Presidio Plugin

ko-pii 규칙을 [Presidio](https://github.com/microsoft/presidio)의 recognizer 형식으로
연결합니다. 아래 예제는 별도의 학습 모델이나 외부 API를 사용하지 않습니다.
Presidio 자체와 spaCy 등 선택 패키지는 설치해야 합니다.

```bash
python -m pip install 'ko-pii[presidio]'
```

## Recognizer 직접 사용

규칙 검출만 필요하면 NLP engine 없이 recognizer를 직접 호출할 수 있습니다.

```python
from ko_pii.integrations.presidio_plugin import KPiiRecognizer

recognizer = KPiiRecognizer(include=["EMAIL"])
results = recognizer.analyze(text="demo@example.com", entities=["EMAIL_ADDRESS"])
```

## AnalyzerEngine에 연결

`AnalyzerEngine()` 기본 설정에 recognizer만 추가해도 한국어 NLP engine이 생기는
것은 아닙니다. 엔진은 recognizer 호출 전에 언어별 전처리를 수행하므로 `ko` 언어의
engine, registry, supported_languages를 모두 맞춥니다.

아래는 [실행 예제](../examples/presidio_rules.py)와 동일하며 실제 SDK CI에서 검사합니다.
blank multilingual tokenizer를 `ko` 슬롯에 연결하고 ko-pii 규칙만 등록합니다.
이는 한국어 형태소 분석이나 통계 NER를 제공하는 설정이 아닙니다.

```python
import spacy
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import SpacyNlpEngine
from presidio_anonymizer import AnonymizerEngine

from ko_pii.integrations.presidio_plugin import KPiiRecognizer


class KoreanRuleEngine(SpacyNlpEngine):
    def load(self):
        # Tokenization only: no model download or statistical NER.
        self.nlp = {"ko": spacy.blank("xx")}


engine = KoreanRuleEngine(models=[{"lang_code": "ko", "model_name": "blank"}])
registry = RecognizerRegistry(supported_languages=["ko"])
registry.add_recognizer(KPiiRecognizer(include=["EMAIL", "PHONE"]))
analyzer = AnalyzerEngine(
    nlp_engine=engine, registry=registry, supported_languages=["ko"],
)
text = "demo@example.com / 010-2345-6789"
results = analyzer.analyze(text=text, language="ko")
print(AnonymizerEngine().anonymize(text=text, analyzer_results=results).text)
```

기존 NLP engine을 사용한다면 해당 engine의 `ko` 지원과 registry 언어를 먼저
확인하십시오. 임의의 엔진 설정을 이 plugin이 자동 수정하거나 모델을 내려받지는 않습니다.

## 지원 라벨

| ko-pii 라벨 | Presidio 라벨 |
|---|---|
| RRN | `KR_RRN` |
| FRN | `KR_FRN` |
| BUSINESS_REG | `KR_BUSINESS_REG` |
| CORP_REG | `KR_CORP_REG` |
| DRIVER_LICENSE | `KR_DRIVER_LICENSE` |
| MEDICAL_INSURANCE | `KR_MEDICAL_INSURANCE` |
| PRESCRIPTION_ID | `KR_PRESCRIPTION_ID` |
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
| PASSPORT | `US_PASSPORT` (기존 호환 매핑, 미국 여권을 검증한다는 뜻 아님) |
| CARD | `CREDIT_CARD` |
| PHONE / FAX | `PHONE_NUMBER` |
| EMAIL | `EMAIL_ADDRESS` |
| IP | `IP_ADDRESS` |
| URL | `URL` |
| PERSON | `PERSON` |

코어의 모든 라벨이 이 adapter에 매핑되는 것은 아닙니다. 표에 없는 라벨은 반환하지
않으며 `KCD`/`KR_KCD`는 지원하지 않습니다. `include`/`exclude`는 ko-pii 라벨을,
`analyzer.analyze(entities=[...])`는 위 Presidio 라벨을 사용합니다.

## 처리와 메타데이터의 범위

`recognition_metadata`에는 `ko_pii_label`, `ko_pii_risk_level`,
`ko_pii_legal_basis`, `ko_pii_evidence`가 포함됩니다. 이는 규칙이 남긴 정보이며
법적 판단이나 도메인 정확도 보장이 아닙니다.

이 adapter는 탐지 결과와 confidence를 넘깁니다. ko-pii Anonymizer의
BLOCK/REVIEW/ALLOW 정책을 자동 적용하지 않습니다. Presidio의 `score_threshold`와
anonymizer operator를 호출자가 설정해야 합니다. 위 예제의 Presidio 치환은 ko-pii의
가역 Vault 토큰화가 아닙니다.
