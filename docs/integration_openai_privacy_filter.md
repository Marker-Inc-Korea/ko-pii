# OpenAI Privacy Filter 연계 가이드

[OpenAI Privacy Filter](https://huggingface.co/openai/privacy-filter)
(Apache-2.0, 2026-04-22) 는 1.5B params 의 다국어 PII 검출 ML 모델이다.
**ko-pii 와 보완성이 강함** — 두 도구를 함께 쓰면 한국 공공 PII 검출의 *룰
기반 한계* 를 ML 자연어 강점으로 보강할 수 있다.

## 빠른 시작

### 설치

```bash
# ko-pii 기본 (룰만, ML 없음)
pip install ko-pii

# Privacy Filter 어댑터 추가 — ML 의존성 옵션
pip install ko-pii[ml]
```

`[ml]` extras 는 `transformers>=4.40`, `torch>=2.0` 을 설치한다. 코어 ko-pii 는
여전히 의존성 0개. GPU 없이도 CPU 추론 가능 (작은 배치 권장).

### 가장 간단한 사용

```python
from ko_pii import Anonymizer, ProcessingMode, get_privacy_filter_adapter

# Privacy Filter 어댑터 — 첫 호출 시 모델 다운로드 (~3GB)
pf = get_privacy_filter_adapter(device="cpu")  # 또는 "cuda" / "mps"

# Hybrid Anonymizer — ko-pii (룰) + Privacy Filter (ML)
anon = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    secondary_detector=pf,
    merge_mode="union",  # 두 결과 합산
)

text = "신청인 홍길동(880101-1234568) 연락처 010-1234-5678, " \
       "민원 내용: 김기덕 감독님께서 제출한 자료에 오류가 있다고 봅니다."

result = anon.process(text)
print(result.text)
# 신청인 <PERSON_1>(<RRN_1>) 연락처 <PHONE_1>, 민원 내용: <PERSON_2> ...
```

## 4가지 병합 모드

### 1. `union` (기본)
양쪽 검출 결과를 *합산*. overlap 시 위험도 높은 쪽 우선. 가장 일반적.

```python
anon = Anonymizer(secondary_detector=pf, merge_mode="union")
```

**장점:** Recall ↑ (한 쪽이 놓친 것도 catch)
**적합:** 표준 운영 환경

### 2. `intersection`
양쪽 *모두* 잡은 것만 인정. high-confidence detection.

```python
anon = Anonymizer(secondary_detector=pf, merge_mode="intersection")
```

**장점:** Precision ↑↑ (FP 거의 0)
**적합:** 엄격한 컴플라이언스 환경 (의료·금융 등)

### 3. `cross_validation`
양쪽 합산하되, *한 쪽만 잡은 것* 은 신뢰도 페널티.

```python
anon = Anonymizer(secondary_detector=pf, merge_mode="cross_validation")
```

**장점:** Recall + 신뢰도 등급 분리
**적합:** 검토 큐 워크플로우 (사람이 한 쪽만 검출된 것 우선 검토)

### 4. `enrich_primary`
ko-pii 결과 우선, Privacy Filter 는 *놓친 영역만* 보강.

```python
anon = Anonymizer(secondary_detector=pf, merge_mode="enrich_primary")
```

**장점:** ko-pii 의 *법적 매핑·도메인 컨텍스트* 보존
**적합:** ko-pii 가 잘하는 부분 (RRN·결정적 PII) 위주 + 자연어 보강

## 시나리오별 권장

### 시나리오 A: 공공기관 내부 — *컴플라이언스 우선*
```python
anon = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    secondary_detector=pf,
    merge_mode="cross_validation",
)
```
- 양쪽 합의된 검출 → 자동 가명화
- 한 쪽만 → REVIEW 큐 (사람 검토)
- 감사 추적·법적 근거 모두 보존

### 시나리오 B: LLM 호출 전 안전 필터 — *recall 우선*
```python
anon = Anonymizer(
    mode=ProcessingMode.PARANOID,  # 낮은 위험도도 차단
    strategy="redact",
    secondary_detector=pf,
    merge_mode="union",
)
clean_text = anon.process(user_input).text
# clean_text → GPT-4 / Claude / Gemini API 안전 전송
```

### 시나리오 C: 빅데이터 일괄 처리 — *속도 vs 정확도*
```python
# 1차: ko-pii (빠름, 결정적) 만으로 처리
fast = Anonymizer(strategy="tokenize")

# 2차: REVIEW 큐의 항목만 PF 로 재평가 (느림, 정확)
slow = Anonymizer(secondary_detector=pf, merge_mode="enrich_primary")
```

## 한국어 성능 예상

Privacy Filter 모델 카드에 따르면:
- 영어: F1 96.5% (PII-Masking-300k)
- 일본어: F1 88.1% (multilingual eval)
- 한국어: *정확한 수치 미공개* — 일본어와 비슷한 수준 추정

ko-pii 단독 KLUE-NER Korean-only F1 = 0.331. 두 도구 union 시 예상:
- **F1 0.7-0.8 수준 도달 가능** (검증은 GPU 환경 필요)
- 결정적 PII (체크섬) 는 ko-pii 가 압도적
- 자연어 인명은 Privacy Filter 가 압도적

## ⚠️ 주의사항

1. **모델 라이센스 확인** — Apache-2.0 (상용 OK). 다만 OpenAI 데이터셋 약관도 확인.
2. **로컬 실행** — 모델 호출은 *외부 API 가 아님*. 데이터 외부 유출 없음.
3. **첫 다운로드 ~3GB** — 인터넷 연결 필요. 이후 캐시.
4. **GPU 없으면 느림** — CPU 추론 시 문서 한 건당 수 초. 대량 처리 시 GPU 권장.
5. **법적 근거 자동 부여 X** — Privacy Filter 출력은 *PII 라벨* 만. ko-pii 가
   결합 처리에서 법적 근거를 부여.
6. **결정성 차이** — ko-pii 룰은 결정성 보장, ML 모델은 모델 버전·환경에 따라
   미세 차이. 감사 추적 시 모델 버전 기록 필요.

## 평가 비교 (벤치마크)

### 재현 명령어

```bash
# ko-pii 단독 (룰만)
python -m ko_pii.eval.kdpii data/kdpii/test.json --person-min-length 3

# ko-pii vs Privacy Filter 직접 비교 (gold = KDPII 실제 인간 라벨)
python -m ko_pii.eval.model_comparison data/kdpii/test.json \
    --mode kdpii --backend onnx --device cpu --cache-dir ./models
```

### 실측 결과 (2026-05-21, KDPII test 4,891 docs)

> **먼저 짚고 가야 할 것 — 두 도구는 비교 대상이 아니라 보완 대상.**
> - **ko-pii**: 한국 공공 부문 PII *전용 설계*. 20+ 라벨 — RRN·FRN·운전면허·여권·사업자·법인 등 *한국 특화 식별번호*가 핵심.
> - **Privacy Filter**: 다국어 *일반 PII* 모델. 8 라벨 (PERSON·EMAIL·PHONE·ADDRESS·DATE·URL·ACCOUNT·SECRET). 영어 중심 (multilingual 11개 언어 중 한국어 부속). 한국 특화 식별번호 라벨이 *학습 스코프 밖*.
>
> 같은 F1 수치를 두 시스템에 적용하면 *모델 성능 비교*가 아니라 *도메인 정의 차이*를 잰다.

#### (가) KDPII 전체 라벨 (20 카테고리, ko-pii 스코프) — 단독 비교

| | ko-pii | Privacy Filter |
|--|------:|--------------:|
| 정탐 / 오탐 / 미탐 | 859 / 297 / 444 | 303 / 630 / 1,003 |
| Micro F1 | 0.699 | 0.271 |

→ Privacy Filter 의 0.271 은 **모델 성능 부족이 아니라 라벨 스코프 부재**. 한국 특화 13 카테고리 (RRN/FRN/PASSPORT/DRIVER_LICENSE/VEHICLE/MAJOR/EDUCATION/POSITION/IP/AGE/HEIGHT/WEIGHT/CARD) 에서 자동 0점. 이 결과의 실제 의미:

> 한국 공공 PII 보호 요구사항 (개인정보 보호법 시행령 제19조 고유식별정보) 을 *Privacy Filter 단독으로는 커버 불가*. 단독 대체 시 critical PII 누출.

#### (나) Privacy Filter 출력 가능 라벨 7종만 — 공정 비교

PERSON · EMAIL · PHONE · ADDRESS · DT_BIRTH · URL · ACCOUNT 한정:

| | ko-pii | Privacy Filter |
|--|------:|--------------:|
| 정탐 / 오탐 / 미탐 | 428 / 225 / 224 | 303 / 630 / 353 |
| Micro F1 | 0.656 | 0.382 |

→ Privacy Filter 의 *홈그라운드 라벨*에서도 한국어 일상 대화체 (KDPII) 에서는 ko-pii 가 더 정확. 주 원인은 학습 분포 차이 (영어 중심 vs 한국 도메인 전용).

#### 카테고리별 상세 — 둘 다 출력 가능한 라벨

| 라벨 | gold | ko-pii F1 | PF F1 | 관찰 |
|------|----:|---------:|------:|------|
| EMAIL | 81 | 1.000 | 0.994 | 거의 동률, 둘 다 신뢰 가능 |
| PHONE | 124 | 0.992 | 0.564 | PF FP 121건 |
| URL | 39 | 0.987 | 0.605 | ko-pii 의 패턴이 더 좁음 |
| ACCOUNT | 77 | 0.819 | 0.360 | PF FP 134건 (account_number 가 catch-all) |
| ADDRESS | 169 | 0.550 | 0.154 | 둘 다 자연어 주소 어려움 |
| DT_BIRTH | 70 | 0.648 | 0.122 | 한국식 날짜 표현이 PF 학습 부족 |
| **PERSON** | 92 | 0.135 | **0.147** | **PF 미세 우위**. KDPII 별명/외자 다수 — ko-pii의 도메인(공식 문서, 직책-anchor)과 다름 |

#### Union 모드 효과 (가설, 실측 미시행)

위 측정은 *단독* 두 시스템. union 모드 (ko-pii + Privacy Filter 결합) 의 실측 효과는 본 보고서 범위 밖. 예상:
- **PERSON recall ↑** — PF 가 별명·외자 더 catch (이 도메인의 약점 보강)
- **EMAIL/PHONE precision** 변동 적음 — 둘 다 이미 0.99+
- **한국 특화 라벨** (RRN 등) ko-pii 단독과 동일 — PF 가 그 라벨을 출력 못함

### 추가 도메인 측정 (2026-05-21)

**KLUE-NER PERSON (신문기사, 한글 풀네임만 평가):**

| 모델 | 문서 | TP | FP | FN | P | R | F1 |
|------|----:|---:|---:|---:|--:|--:|--:|
| ko-pii | 5,000 | 980 | 1,790 | 932 | 0.354 | 0.513 | **0.419** |
| Privacy Filter (1,000 sample) | 1,000 | 24 | 9 | 389 | 0.727 | **0.058** | **0.108** |

→ openai/PF 가 한국어 신문기사 풀네임의 **94% 를 미탐**. precision 은 0.727 로 높지만, 한국어 학습 분포가 약해 *catch 자체* 가 적음. ko-pii 의 룰 기반 검출이 이런 도메인에 강함.

**PII 주입 코퍼스 (실데이터 + 합성 PII):**

기존 합성 (13 템플릿) 의 과적합 가능성을 우회하려고 새로 만든 코퍼스. AI Hub 569 행정문서 본문 200 문단 (양 모델 모두 학습 노출 없음) 에 합성 PII 를 10가지 anchor 패턴으로 주입. Gold 1,043 spans.

| 카테고리 | gold | ko-pii F1 | PF F1 |
|---------|----:|---------:|------:|
| ACCOUNT | 23 | 1.000 | 0.189 (PF FP 198) |
| ADDRESS | 72 | 0.980 | 0.354 (PF FP 202) |
| BUSINESS_REG | 34 | 1.000 | 0.000 (PF 라벨 부재) |
| DRIVER_LICENSE | 8 | 1.000 | 0.000 |
| EMAIL | 39 | 1.000 | 0.987 |
| PASSPORT | 12 | 1.000 | 0.000 |
| PERSON | 453 | 0.795 | **0.600** |
| PHONE | 306 | 1.000 | 0.862 |
| RRN | 72 | 1.000 | 0.000 |
| VEHICLE | 24 | 1.000 | 0.000 |
| **micro** | **1,043** | **0.901** | **0.507** |

→ **anchor 가 강한 도메인 (필드 라벨·서명·괄호) 에서는 PF 의 한국어 PERSON 검출이 F1 0.600** — KDPII (0.147) / KLUE-NER (0.108) 보다 훨씬 향상. 즉 PF 도 "한국어가 약하다" 가 아니라 "anchor 없는 자연어 인명에 약하다".

PF 의 두드러진 약점:
- `account_number` catch-all: 행정문서 숫자열을 잘못 ACCOUNT 로 → 198 FP
- `private_date` 과탐: 한국식 날짜 표현 → 250 FP (ko-pii DT_BIRTH 4 FP)
- 한국 특화 라벨 부재: BUSINESS_REG/DRIVER_LICENSE/PASSPORT/RRN/VEHICLE 153 gold 전체 자동 FN

재현 방법:
```bash
# 1. inject 코퍼스 생성
python data/inject_pii_corpus.py -n 200 --seed 0

# 2. 두 검출기 비교
python data/eval_injected_corpus.py data/corpus/injected_pii_corpus.jsonl
```

### 솔직한 결론

본 평가는 **"ko-pii vs Privacy Filter 누가 이기느냐"** 의 답이 아니다.

> 두 도구는 *다른 목적용*. 한국 공공 부문 배포 시 Privacy Filter 단독 사용은 부적합 (라벨 스코프). ko-pii 의 한국 특화 + Privacy Filter 의 일반 PII 자연어 강점을 *결합 (union 모드)* 하는 게 본 문서의 권장. 본 섹션 위 4가지 병합 모드 (union/intersection/cross_validation/enrich_primary) 가 그 통합의 도구.

진정한 head-to-head 비교 대상은 **OpenMed/privacy-filter-multilingual** (한국어 공식 지원, 217 라벨 — ko-pii 의 다수 카테고리 커버). 본 평가에는 미포함 (torch 버전 매칭 이슈로 제외 — 추가 평가 계획 없음).

상세 분석 + 카테고리 풀 표: [`docs/EVALUATION_REPORT.md`](EVALUATION_REPORT.md) §1-bis + §2. 원본 평가 출력: `data/corpus/kdpii_3way_full.txt`.

## 데이터 출처

- [openai/privacy-filter (Hugging Face)](https://huggingface.co/openai/privacy-filter)
- [OpenAI Privacy Filter Model Card](https://cdn.openai.com/pdf/c66281ed-b638-456a-8ce1-97e9f5264a90/OpenAI-Privacy-Filter-Model-Card.pdf)
- [GitHub: openai/privacy-filter](https://github.com/openai/privacy-filter)
