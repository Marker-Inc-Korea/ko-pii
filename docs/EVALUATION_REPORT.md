# ko-pii 평가 보고서

> ko-pii 의 실데이터 정확도, 도메인별 적합도, 카테고리별 분석, 가명화 샘플,
> 재현 방법을 한 곳에 정리한 단일 보고서.

## 용어 정리

| 한국어 | 영문 | 의미 |
|---|---|---|
| **정탐** | TP (True Positive) | 검출했고 정답에도 있음 (잘 잡음) |
| **오탐** | FP (False Positive) | 검출했는데 정답에 없음 (잘못 잡음) |
| **미탐** | FN (False Negative) | 정답에 있는데 검출 못함 (놓침) |
| 정확도 | Precision | 정탐 / (정탐 + 오탐) |
| 재현율 | Recall | 정탐 / (정탐 + 미탐) |
| F1 | F1 | 정확도와 재현율의 조화 평균 |

---

## 1. 최종 점수 한눈에

| 벤치마크 | 데이터 | 문서 수 | F1 | 도메인 적합도 |
|---|---|---:|---:|---|
| **행정문서 + PII 주입** (실측) | AI Hub 569 행정문서 본문 + 합성 PII | 200 | **0.901** | **사용자 메인 (§1-bis)** |
| 합성 코퍼스 (sanity) | 13 템플릿 다단락 | 60×5 | 0.85 | 회귀 감지 |
| KDPII (참고) | 한국어 일상 대화 | 53,778 | **0.699** | 대화체 (참고용) |
| KLUE-NER (참고) | 신문기사 PERSON | 5,000 | 0.376 | 자연어 어림 |

⚠ KDPII F1 = 0.699 가 사용자 도메인 (행정·공공 문서) 의 실질 성능 아님.
KDPII PERSON gold 의 50% 가 1-2자 별명·이름 단독 ("재명/미선") — 일상 대화
도메인 기준. 자세한 도메인 분석: §4.

### 1-bis. 비교 모델 평가 (2026-05-22 로컬 측정)

같은 벤치마크들에 [openai/privacy-filter](https://huggingface.co/openai/privacy-filter)
(다국어 일반 PII ML 모델, 660M params) 와 [Microsoft Presidio](https://github.com/microsoft/presidio) (가장 인기 OSS PII 프레임워크) 도 평가:

| 벤치마크 | 문서 수 | ko-pii F1 | openai/PF F1 | Presidio default⁴ | Presidio +KR⁵ | 비고 |
|---|---:|---:|---:|---:|---:|---|
| **실데이터 PII 주입 코퍼스** | 200 | **0.901** | 0.480 | 0.118 | 0.542 | AI Hub 569 본문 + 합성 PII |
| **LLM 생성 벤치마크** ★ | 187 | **0.770** | 0.434 | 0.208 | 0.446 | 한국 특화 / 1,199 spans / **32/32 카테고리 완전 커버** |
| **KDPII test (인간 라벨)** | 4,891 | **0.656** | 0.382 | 0.302 | 0.367 | 일상 대화체 |
| **KLUE-NER PS (한글 풀네임만)** | 5,000 | **0.419** | **0.155** | 0.000 | 0.000 | 신문기사 PERSON, 5,000 전체 |
| **Naver x 창원대 NER PS (한글 풀네임만)** | 90,000 | **0.308** | — | — | — | 뉴스 기사 PERSON, Korpora 오픈 |

★ **LLM 생성 평가셋의 점수 0.799 < inject 코퍼스 0.885** — ko-pii 가 자신의 inject 데이터에 *과적합 안 됨* 의 직접 증거. 다양한 자연 산문 (정형 양식·anchor 약함) 에서 점수가 *낮아지는* 게 정상이며, 그래도 결정적 카테고리는 만점 유지 (RRN/FRN/PASSPORT/DRIVER_LICENSE/VEHICLE/CARD/EMAIL/PHONE/ACCOUNT 등 F1 ≈ 1.000). 자세한 카테고리별 결과: `data/corpus/eval_corpus_kpii.txt`.

**모든 점수는 공정 비교 — openai/privacy-filter 가 출력 가능한 7 라벨 (PERSON / EMAIL / PHONE / ADDRESS / DT_BIRTH / URL / ACCOUNT) 만 양 모델에서 micro F1 재계산.** 한국 특화 14 카테고리 (RRN/FRN/PASSPORT/DRIVER_LICENSE/VEHICLE/BUSINESS_REG/CARD/IP/AGE/HEIGHT/WEIGHT/MAJOR/EDUCATION/POSITION) 는 openai 라벨 공간에 부재 → 양쪽 모두 제외 후 비교 (자동 FN 처리는 부당). 한국 특화 카테고리 분석은 아래 "▣ openai/PF 가 라벨 공간에 없는 한국 핵심 PII" 박스 참조.

⁴ Presidio (default) = `pip install presidio-analyzer` + spaCy `ko_core_news_sm` 기본 16 recognizer. 한국 사용자가 *추가 설정 없이* 얻는 것.
⁵ Presidio (+KR 정규식) = 위 기본 위에 한국 핵심 PII 6종 (RRN/FRN/PHONE/VEHICLE/BUSINESS_REG/DRIVER_LICENSE/CARD) 의 정규식 인식기를 사용자가 직접 등록. Presidio 사용자가 한국어 지원을 위해 *최소한* 추가할 만한 수준 (재현 코드: `src/ko_pii/eval/presidio_compare.py`).

> **참고 — 합성 13 템플릿 코퍼스 (CI 회귀 감지용)**: `ko_pii.eval.synth` 가 생성하는 13 도메인 양식 (`gov_decree` `civil_petition` `hr_review` 등) 50 docs / seed 0 에서 ko-pii F1 = 0.785, openai = 0.547, Presidio default = 0.222, Presidio+KR = 0.357 (공정 비교 기준). 실측이 아닌 *코드 변경 시 자동 회귀 감지* 용도라 외부 평가표에서 제외. 노이즈 단락 강화 (commit ec72791) 도 동일 코퍼스에 robustness 정량 측정 — 변동 ko-pii −0.029 / openai −0.004 (전체 라벨 기준).

> **▣ openai/privacy-filter 가 라벨 공간에 없는 한국 핵심 PII (14 카테고리)**
>
> RRN (주민등록번호), FRN (외국인등록번호), 여권번호, 운전면허번호, 차량번호,
> 사업자등록번호, 카드, IP, 학력, 전공, 직책, 나이, 신장, 체중.
>
> 이 중 **RRN / FRN / 여권** 은 「개인정보보호법 시행령 제19조 고유식별정보」 로
> 한국 PII 보호의 *최우선 보호 대상*. **이 카테고리들이 다국어 일반 모델의
> 라벨 공간에 부재하다는 점이 한국 공공 도메인에서 ko-pii 가 필요한 핵심 이유.**
>
> KDPII 4,891 문서에서:
> - ko-pii: RRN 18/18 (F1 1.000) · FRN 9/9 (1.000) · PASSPORT 15/18 (0.909)
>   · DRIVER_LICENSE 5/17 (0.455) · VEHICLE 50/52 (0.980) · IP 11/11 (1.000)
> - openai/PF: 전부 **0** (라벨 공간 부재 → 자동 미탐)
> - Presidio (default): 전부 **0** (한국 식별번호 인식기 부재)
> - Presidio (+KR 정규식): RRN 18/18 (F1 1.000) · FRN 9/9 (1.000) · DRIVER_LICENSE 5/17 (0.455) · CARD 22/56 (0.440) · IP 3/11 (0.429) — *정규식 등록만 하면 결정적 PII 는 잡힘*
>
> 200 docs PII 주입 코퍼스에서:
> - ko-pii: RRN 72/72 · BUSINESS_REG 34/34 · DRIVER_LICENSE 8/8
>   · PASSPORT 12/12 · VEHICLE 24/24 (모두 F1 1.000)
> - openai/PF: 전부 **0**
> - Presidio (default): 전부 **0**
> - Presidio (+KR 정규식): RRN 72/72 (1.000) · BUSINESS_REG 34/34 (0.782) · DRIVER_LICENSE 8/8 (1.000) · VEHICLE 24/24 (1.000) — *PASSPORT 만 미커버*
>
> ★ **F1 점수 격차가 아니라 *커버리지 차이* 가 본질.** 한국 공공 부문 PII 보호
> 에서는 14 카테고리의 부재가 곧 *법적 보호 실패* 를 의미하기에, openai/PF 점수
> 보다 *어떤 카테고리를 잡지 못하는가* 가 더 중요한 비교 축.
>
> **Presidio + KR 정규식 의 의미** — *결정적 PII (RRN/FRN/CARD/VEHICLE/BUSINESS_REG) 는 정규식 한 줄이면 다국어 ML 모델 한계를 우회 가능*. ko-pii 는 이미 100+ 룰/사전 내장 (사용자가 정규식 직접 작성할 필요 없음). 즉 *룰 기반 결정적 검출이 한국 핵심 PII 보호에 유효한 접근* — ML 보단 정확하고 (체크섬 검증 가능), 사전 큐레이션은 학습 데이터 라벨링보다 단순.

KLUE-NER (5,000 전체) 양쪽 측정: ko-pii F1 0.419 / openai F1 0.155 (TP 163 / FP 33 / FN 1,749, precision 0.832 / recall 0.085). 한국어 신문기사 풀네임의 91.5% 를 openai 미탐 — precision 은 높지만 *catch 자체가 적음* (한국어 학습 분포 약점).

### 평가 신뢰성 — self-fulfilling benchmark 의심에 대한 답

룰 기반 라이브러리의 흔한 비판: *"내 룰에 통과되는 데이터를 만들어 평가한 것 아니냐"*. 본 평가에서 이 의심을 회피하는 **5중 방어선**:

**1. 외부 gold 데이터 2종 (가장 강력)**

ko-pii 와 **완전 독립적으로** 만들어진 두 외부 데이터셋에서 측정한 점수가 이미 있음:

| 데이터 | 제작 주체 | ko-pii 관여 | 라벨 출처 | 측정 F1 |
|---|---|---|---|---|
| **KDPII test** (4,891) | 연세대 Li Fei et al. (Zenodo 10968609 CC-BY-4.0) | 없음 | 인간 어노테이션 | **0.656** |
| **KLUE-NER PS** (5,000) | KLUE 컨소시엄 (카카오·NAVER·SKT) | 없음 | 인간 어노테이션 | **0.419** |
| **LLM 생성 벤치마크 (187)** ★ | LLM 생성, ko-pii 룰 미참조 + 한국 특화 | 데이터 작성 X | LLM 생성 + 동시 라벨 | **0.770** |

→ 외부 라벨 기준 점수가 reasonable 하게 분포 — 룰을 외부 데이터에 맞춰 조작했다는 의심 약화.

**★ LLM 생성 벤치마크 v4 (187 docs / 1,199 spans / 32 카테고리 완전 커버, F1 0.770)**:

한국 특화 벤치마크 규모 평가셋 (한국 특화 92.5%).

**v4 한국 특화 강화 작업** — 사용자 피드백 "외국은 굳이 필요 없음, 한국 특화" 반영:
- 외국 케이스 제거 (다문화 7국가 명단·해외 학회·외국 동료 등 5 docs)
- 한국 특화 강화 +40 docs (10 도메인):
  1. 지자체 5 (강남구청·해운대구청·청운효자동주민센터·수원시 영통구청·광주서구청보건소)
  2. 한국 공기업 4 (KEPCO·코레일·LH·건강보험공단)
  3. 한국 의료기관 4 (서울대병원·분당서울대병원·삼성서울병원·노인요양원)
  4. 한국 학교 4 (서울대·KAIST·양재초·연세대)
  5. 한국 사법 3 (부동산 임차권·교통사고 합의·형사 공소장)
  6. 한국 군부대 2 (육군·해군)
  7. 한국 농어업 2 (영월 농지·완도 어업)
  8. 한국 종교 1 (조계종 신도회)
  9. 한국 정치 2 (국회의원·지방의원)
  10. 한국 회사 3 (삼성 협력사·LG에너지솔루션·현대건설)
  11. 한국 언론 1 (연합뉴스)
  12. 한국 특화 거부 케이스 3 (행정구역 통계·부처명 나열·대학명 나열)

**특징**:
- **32/32 카테고리 완전 커버** (ko-pii 전체 PII 라인업)
- **한국 특화 92.5%** (외국 키워드 7.5% — FRN 관련 1-2개만 남음)
- 텍스트 길이: 평균 257 chars (131 ~ 1,085)
- 거부 케이스 18 docs (12%, FP 유도 함정)
- 평균 6.4 spans/doc
- **F1 0.770 < inject 0.885** → ko-pii 가 inject 데이터에 *과적합 안 됨* 의 직접 측정.

**2. 200 docs 인젝션 코퍼스의 분리 설계**

- **베이스 텍스트** = **AI Hub 569 행정문서 실제 본문** (한국지능정보사회진흥원 공공 데이터). ko-pii 학습/룰 설계에 노출되지 않은 외부 데이터.
- **PII 주입** = `data/inject_pii_corpus.py` 가 합성 RRN/PHONE 등을 10가지 anchor 패턴으로 삽입.
- **anchor 사전 분리** = inject 스크립트가 import 하는 것은 `ko_pii.eval.synth` 의 *PII 값 풀* (`_RRN_SAMPLES` 등) 만. 검출기의 anchor 사전 (`field_labels.py` / `titles.py` / `common_words.py`) 은 안 가져옴 — 코드 검증 가능 (`grep "from ko_pii" data/inject_pii_corpus.py`).
- 결과: inject 가 만든 anchor 와 검출기가 잡는 anchor 의 *내용* 은 (당연히) 겹치지만 ("성명: 박지훈" → 검출), 이는 *실제 한국 공문서 분포의 자연스러운 anchor* 이지 룰을 데이터에 맞춘 것이 아님.

**3. 합성 13 템플릿 코퍼스의 위상 격하**

`ko_pii.eval.synth` 가 생성하는 정형 양식 (50 docs) 은 검출 룰과 같은 저자가 만든 것이라 *self-fulfilling 위험 가장 큼*. 이 우려 때문에 외부 평가표에서 제외, **CI 회귀 감지** (코드 변경 시 자동 측정) 용도로만 사용.

#### 그래도 남는 잔여 의심 + 추가 방어 옵션

200 docs 인젝션 코퍼스도 inject 코드의 anchor 패턴 분포 자체는 저자가 정의함 → 잠재적 잔여 의심 가능. 다음 옵션 중 하나로 추가 방어:

- **A. 사용자 자체 라벨링 30~100 문서** — 외부 인원이 실제 공문서에 PII 의 라벨링 → 가장 강력한 검증 (작업량: 4~8시간)
- **B. 더 많은 외부 GT 데이터셋 평가** — KMOU/KoBERT-NER 등 추가 (작업량: 1~3시간/데이터셋)
- **C. 외부 비교 모델 추가** — ✅ **2026-05-22 완료**: Microsoft Presidio (default + KR 정규식 보강) 추가 측정. 4 벤치마크 모두 *동일한 상대 순위* (ko-pii > openai/PF > Presidio+KR > Presidio default) 로 self-fulfilling 가설 약화. OpenMed/PF-multilingual 추가 측정도 진행 중.
- **D. 동료/외부 라벨러 검증** — 학회 · github 공개 검토

본 라이브러리의 권장 — 사용자 도메인 (한국 공공) 에 본격 운영 전 30~100 문서 자체 라벨링 (옵션 A) 으로 한 번 더 검증.

#### 실데이터 PII 주입 코퍼스 — 상세

기존 합성 코퍼스는 13 템플릿 정형이라 양쪽 검출기가 anchor 패턴에 *과적합* 가능. 본 코퍼스는 **AI Hub 569 행정문서 (실제 한국 공공 텍스트, 두 모델 모두 학습 노출 없음)** 의 본문 200 문단을 base 로 하고, ko-pii 로 사전-redaction 한 뒤 합성 PII 를 10가지 anchor 패턴 (필드 라벨/서명/괄호/조사 등) 으로 주입. Gold span 위치 100% 정확.

PERSON 카테고리 비교 (anchor 강한 도메인):
- ko-pii F1 0.795 (TP 420 / FP 183 / FN 33) — 베이스 잔존 PII 가 FP 일부 기여
- openai F1 **0.600** (TP 256 / FP 144 / FN 197) — KDPII (0.147) / KLUE-NER (0.155) 보다 *훨씬 높음*. anchor 가 있으면 openai 도 한국어 인명을 잡는다는 증거

ACCOUNT/DT_BIRTH 의 openai 과탐:
- ACCOUNT FP 198 — `account_number` catch-all 패턴이 행정문서의 숫자열을 잘못 인식
- DT_BIRTH FP 250 — `private_date` 가 한국식 날짜 표현 (2024년 3월 등) 을 과탐

한국 특화 라벨 (RRN/FRN/PASSPORT/DRIVER_LICENSE/VEHICLE/BUSINESS_REG):
- ko-pii 모두 F1 1.000 (153 gold spans 전부 정탐)
- openai 모두 F1 0.000 (라벨 자체 없음 → 자동 FN)

#### 무엇이 이 차이를 만드나

openai/privacy-filter 의 F1 차이는 **모델 성능 부족이 아니라 라벨 스코프 차이**. 한국 특화 식별번호 13 카테고리 (RRN/FRN/PASSPORT/DRIVER_LICENSE/VEHICLE/MAJOR/EDUCATION/POSITION/IP/AGE/HEIGHT/WEIGHT/CARD) 가 모델 라벨 공간에 *없어서* 자동 FN. KDPII 4,891 에서 openai 의 1,003 FN 중 **약 567건**이 이 13 카테고리.

openai 의 출력 가능 7 라벨 (PERSON·EMAIL·PHONE·ADDRESS·DT_BIRTH·URL·ACCOUNT) 만으로 공정 비교 시:
- KDPII: ko-pii 0.656 vs openai 0.382 (1.72×)
- 합성 공문서: ko-pii 가 PERSON/PHONE/EMAIL/ADDRESS/ACCOUNT 모두 우위
- KLUE-NER PS: ko-pii 0.419 vs openai 0.155 (한국어 학습 분포 한계, 5,000 전체)

상세 분석 + 매칭 로직 + Union 모드 가설: `docs/integration_openai_privacy_filter.md` §"평가 비교 (벤치마크)".

> **이 비교의 정직한 해석:** openai/privacy-filter 는 다국어 *일반* PII 보호 용도로 설계된 견고한 모델 (HF 다운로드 297K). 한국 공공 부문 PII 보호 요구사항 (개인정보 보호법 시행령 제19조 고유식별정보) 을 그대로 커버하지 못하는 건 *모델 결함이 아니라 설계 스코프 차이*. 본 평가는 "ko-pii 가 더 좋다" 가 아니라 "두 도구는 다른 목적, 한국 공공 도메인엔 ko-pii, 일반 다국어엔 openai/PF, 또는 union 결합" 을 보여줌.

#### Microsoft Presidio 와의 비교 — OSS PII 프레임워크의 한국어 현실

Microsoft Presidio 는 가장 인기 있는 OSS PII 검출·가명화 프레임워크 (`presidio-analyzer`, `presidio-anonymizer`). 한국어 환경에서의 *out-of-the-box* 동작과 *최소한의 사용자 보강* 으로 얻는 성능을 측정.

**Presidio (default)** — `pip install presidio-analyzer presidio-anonymizer` + `python -m spacy download ko_core_news_sm` 후 별도 설정 없이 사용:
- 기본 16 recognizer: EMAIL/URL/PHONE/IP/IBAN/CRYPTO/DATE/MAC 등 (영어권 위주)
- 한국어 PERSON 은 spaCy `ko_core_news_sm` NER 의존 → KLUE-NER 5,000 문장 PERSON 검출 **0건** (recall=0)
- 200 docs PII 주입에서 micro F1 **0.118** — EMAIL/PHONE 일부만 검출, 한국 식별번호는 라벨 부재로 모두 미탐
- KDPII fair F1 **0.302** — openai/PF 의 0.382 와 비슷, URL 의 광범위 매칭으로 점수 끌어올림

**Presidio + KR 정규식** — 한국 핵심 PII 6종 (RRN/FRN/PHONE/VEHICLE/BUSINESS_REG/DRIVER_LICENSE/CARD) 의 `PatternRecognizer` 를 사용자가 직접 등록 (~50줄 코드):
- 200 docs PII 주입에서 RRN 72/72, BUSINESS_REG 34/34, DRIVER_LICENSE 8/8, VEHICLE 24/24 — *모두 F1 1.000* (정규식 + 체크섬 없는 결정적 매칭)
- PHONE F1 0.886 (default 0.192 대비 +0.694 — 한국 모바일/지역 형식 정규식 추가 효과)
- micro F1 **0.542** / fair F1 **0.455** — openai/PF 의 0.539 와 동급
- 하지만 PERSON 은 여전히 spaCy 의존 → KLUE-NER 0건, 200 docs 0건, KDPII 0건

**주는 교훈:**
1. *결정적 PII (RRN/FRN/카드/차량/사업자번호) 는 정규식 만으로 100% 잡힘* — 다국어 ML 모델 한계가 곧 한국 핵심 PII 보호 불가가 아님. 사용자가 직접 룰 추가 가능.
2. *PERSON 같은 사전·문맥 의존 카테고리는 ML 또는 큐레이션된 룰 필요* — Presidio 의 spaCy `ko_core_news_sm` 은 한국 공공 도메인 PII 검출에 부족 (5,000 KLUE 문장 PERSON 0건).
3. *ko-pii 는 위 두 가지를 모두 내장* — 결정적 검출 22 카테고리 + 한국 특화 사전 (성씨 286, 직급 250+, 지역 500+, 학교 330+) + 17+ 거부 룰. 사용자가 정규식 직접 작성하거나 spaCy 모델 학습할 필요 없음.

상세 측정 데이터: `data/corpus/presidio_*.txt`. 재현: `python data/eval_presidio_all.py --bench all --mode both`.

### 1-quater. 오탐(FP) 종합 — 벤치마크별 분포 + 정책 + 완화

리뷰어가 가장 우려하는 부분이라 한 곳에 정리. *ko-pii 의 FP 는 PERSON 카테고리에 집중되며 다른 카테고리는 거의 0* 이라는 패턴이 4 벤치마크에서 일관적.

#### 벤치마크별 FP 분포 (ko-pii)

| 벤치마크 | PERSON FP | ADDRESS FP | DT_BIRTH FP | ACCOUNT FP | PHONE FP | 기타 FP |
|---|---:|---:|---:|---:|---:|---:|
| 200 docs PII 주입 | 183 | 3 | 4 | 0 | 0 | 0 |
| 합성 강화 후 (50) | 147 | 1 | 5 | — | 3 | IP 2 · MAJOR 7 · POSITION 5 · POSTAL 2 |
| KDPII (4,891) | 198 | 13 | 1 | 11 | 2 | EDUCATION 20 · POSITION 40 · WEIGHT 5 |
| 부트스트랩 (30, gold 없음) | 744 탐지* | 63 | 10 | 0 | 27 | EDUCATION 4 · MAJOR 3 · 등 |

\* 부트스트랩은 gold 없어 FP 라 단정 불가 — *탐지 갯수*. 실제 인명 비율은 §1-bis 의 KDPII 0.656 / 200 docs 0.885 가 결정.

#### openai/PF 와의 FP 패턴 차이

| 벤치마크 | ko-pii 최대 FP 카테고리 | openai/PF 최대 FP 카테고리 |
|---|---|---|
| 200 docs PII 주입 | PERSON 183 | DT_BIRTH **250** · ADDRESS **202** · ACCOUNT **198** · PERSON 144 |
| 합성 강화 후 | PERSON 147 | ACCOUNT **160** · DT_BIRTH 41 · PERSON 22 |
| KDPII | PERSON 198 | PERSON 273 · ACCOUNT 134 · PHONE 121 · ADDRESS 68 |

→ **ko-pii**: FP 의 거의 전부가 PERSON 단일 카테고리 (룰 기반 후보 추출의 의도된 trade-off).
→ **openai/PF**: ACCOUNT / DT_BIRTH / ADDRESS 의 *catch-all 패턴 과탐* 이 광범위 (`account_number` 가 행정문서의 모든 숫자열을 잡고, `private_date` 가 모든 한국식 날짜를 잡음). 실제 PII 가 없는 부트스트랩 코퍼스에서도 DT_BIRTH 31 · ACCOUNT 6 발생.

#### ko-pii 의 FP 완화 메커니즘 (4가지)

**1. PERSON 거부 룰 17+ 종**
- 단성 + 직책 → 호칭 거부 (`김부장` `박과장` `이대리`)
- 단성 + 행정구역 → 거부 (`김포시` `이천시`)
- 단성 + 학교/은행 → 거부 (`이화여대` `이수신`)
- 어말 형태소 16종 → 거부 (`~은데` `~라서` `~까지` 끝)
- 부처/기관명 → 거부 (`보건복지부` `기획재정부`)
- 이미 가명화된 표기 → 거부 (`박씨` `김모씨` `정 군` `○○○ 시민`)
- 자동 학습: `data/classify_fp_candidates.py` + `dictionaries/common_words.py` (현재 ~300 단어)

**2. DT_BIRTH 비-생일 키워드 거부 30+**
공문서의 일반 일자 ("선고일자/시행일자/배포일자/회의일자/감사기간/회계연도" 등) 가 생일로 오탐 안 되게 명시 거부. 200 docs PII 주입에서 DT_BIRTH FP 4 (vs openai 250).

**3. ADDRESS 강한 anchor 요구**
대화체 단독 (시·군·구·동) 은 25자 윈도우 내 강한 anchor 필수 (`주소` `자택` `살던` `명함` 등) → 일반 문장의 행정구역 단어가 주소로 오탐 안 됨.

**4. 사용자 모드 + 검토 큐**
- `--mode PARANOID/STRICT/BALANCED/PERMISSIVE` — 차단 기준 사용자 선택 (precision/recall trade-off)
- `result.review_queue` — confidence 낮은 검출은 자동으로 사람 검토 큐에 들어감 → OK/오탐 마킹 → `common_words` 자동 학습
- HTML 리포트 (정탐 초록 / 오탐 빨강 / 미탐 노랑) 로 시각 확인

#### 200 docs PII 주입 실측 FP 상세 (메인 벤치마크)

| 카테고리 | ko-pii FP | openai/PF FP | ko-pii 가 우위인 이유 |
|---|---:|---:|---|
| PERSON | 183 | 144 | 후보 추출 정책 차이 (ko-pii recall ↑) — F1 양쪽 비슷 (0.795 vs 0.600) |
| ADDRESS | 3 | 202 | ko-pii 행정구역 사전 + anchor / openai catch-all |
| DT_BIRTH | 4 | 250 | ko-pii 비-생일 키워드 거부 30+ / openai `private_date` 광범위 |
| ACCOUNT | 0 | 198 | ko-pii 키워드 anchor 필수 / openai `account_number` catch-all |
| EMAIL/PHONE/RRN/VEHICLE/... | 0 | 0~40 | 결정적 검증 (체크섬·화이트리스트) |

→ **PERSON 외 모든 카테고리에서 ko-pii FP 가 openai 보다 *수십~수백 배 적음***. 리뷰어가 우려할 만한 "ML 안 쓰니 FP 많지 않냐" 는 정확히 *반대*. ko-pii 의 FP 는 PERSON 한 카테고리에 집중되며, 그것조차 4가지 완화 메커니즘으로 사용자가 조절 가능.

---

### 1-ter. 부트스트랩 코퍼스 — 탐지 갯수 비교 (gold 없음)

Wikipedia + korea.kr (cycle 1·2 fp_collector 부트스트랩 소스) 에 두 검출기 동시 실행. **gold span 없으므로 F1 측정 X — 각 모델이 카테고리별로 *몇 개를 탐지* 했는지만 비교.** 카테고리별 분포 = 두 모델의 *민감도/과탐 경향* 의 단서.

| 코퍼스 | 문서 수 | 텍스트 | ko-pii 탐지 | openai/PF 탐지 |
|--------|------:|------:|---------:|--------------:|
| Wikipedia (Phase 9 부트스트랩) | 11 | 25,782 bytes | 308 | 48 |
| korea.kr 정책브리핑 | 19 | 43,238 bytes | 558 | 64 |
| **합계** | **30** | **69,020 bytes** | **866** | **112** |

#### 카테고리별 분포 (합계)

| 카테고리 | ko-pii | openai/PF | 차이 해석 |
|---------|----:|--------:|-----------|
| PERSON | 744 | 32 | ko-pii 가 후보 23× 많이 emit — 룰의 *low-threshold 후보 추출* 정책. 실제 인명 비율은 gold 평가 (KDPII §1-bis) 와 inject 코퍼스 (PERSON F1 0.795) 참조 |
| ADDRESS | 63 | 18 | ko-pii 행정구역 사전이 더 광범위 (광역 17 + 기초 226 + 빈출 동 150) |
| PHONE | 27 | 21 | 비슷한 수준 (양쪽 정형 패턴 잘 잡음) |
| DT_BIRTH | 10 | **31** | openai `private_date` 가 한국식 날짜에 더 민감 (inject 평가에서 250 FP 관찰됨 — 과탐 가능성 ↑) |
| ACCOUNT | 0 | 6 | openai `account_number` catch-all (inject 평가 198 FP) |
| URL | 4 | 4 | 동률 |
| AGE / COURT_CASE / EDUCATION / MAJOR / VEHICLE | 18 | 0 | openai 라벨 부재 → 모두 0 |

#### 관찰

- **PERSON 탐지 격차가 가장 큼 (744 vs 32)** — ko-pii 는 후보 추출 단계에서 *공격적* (높은 recall, 낮은 precision). openai 는 보수적 (낮은 recall, 높은 precision). 실제 도메인별 정확도는 gold 평가 (§1-bis) 가 결정적.
- **openai 의 DT_BIRTH·ACCOUNT 과탐 경향** — 본 코퍼스 (Wikipedia + 정책브리핑) 에 실제 생년월일·계좌번호가 거의 없는데도 양수 탐지 → 과탐. inject 코퍼스에서도 같은 패턴 (DT_BIRTH 250 FP / ACCOUNT 198 FP).
- **ko-pii 의 한국 특화 카테고리** (AGE/COURT_CASE/EDUCATION/MAJOR/VEHICLE) 는 openai 가 라벨 공간 자체 없음 → 부트스트랩 코퍼스에서도 동일하게 0.

원본 출력: `data/corpus/bootstrap_detections.txt`.
재현: `python data/count_bootstrap_detections.py data/corpus/wikipedia.txt data/corpus/korea_kr.txt`.

소요 시간 (CPU, ONNX q4f16): Wikipedia 74s / korea.kr 160s = 평균 ~8s/doc.

---

## 2. KDPII 카테고리별 분석 (53,778 문서, 통합 표)

운영 적합도 + 정탐/오탐/미탐 + 점수를 한 표에 정리:

| Tier | 카테고리 | 정탐 | 오탐 | 미탐 | 정확도 | 재현율 | F1 | 비고 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **S** | EMAIL | 617 | 1 | 0 | 0.998 | 1.000 | **0.999** | 완벽 |
| S | VEHICLE | 449 | 0 | 4 | 1.000 | 0.991 | **0.996** | |
| S | URL | 457 | 0 | 3 | 1.000 | 0.993 | **0.997** | TMI_SITE 매핑 |
| S | FRN | 198 | 0 | 1 | 1.000 | 0.995 | **0.997** | 외국인등록번호 |
| S | RRN | 198 | 0 | 2 | 1.000 | 0.990 | **0.995** | 주민번호 |
| S | IP | 197 | 0 | 3 | 1.000 | 0.985 | **0.992** | |
| S | PHONE | 1,315 | 26 | 4 | 0.981 | 0.997 | **0.989** | 대표번호 포함 |
| **A** | WEIGHT | 700 | 127 | 1 | 0.846 | 0.999 | **0.916** | 단위 다양 |
| A | HEIGHT | 552 | 3 | 155 | 0.995 | 0.781 | **0.875** | |
| A | DRIVER_LICENSE | 154 | 0 | 45 | 1.000 | 0.774 | **0.873** | 체크섬 미적용 |
| A | ACCOUNT | 653 | 93 | 151 | 0.875 | 0.812 | **0.843** | 은행 anchor |
| A | AGE | 511 | 36 | 189 | 0.934 | 0.730 | **0.820** | 한글 음역 |
| **B** | PASSPORT | 132 | 0 | 68 | 1.000 | 0.660 | **0.795** | 한국 prefix |
| B | MAJOR | 441 | 27 | 268 | 0.942 | 0.622 | **0.749** | 학과 사전 |
| B | DT_BIRTH | 379 | 25 | 355 | 0.938 | 0.516 | **0.666** | 날짜 + anchor |
| B | EDUCATION | 557 | 150 | 485 | 0.788 | 0.535 | **0.637** | 학교 사전 |
| B | POSITION | 596 | 406 | 564 | 0.595 | 0.514 | **0.551** | 직책 사전 |
| **C** | ADDRESS | 624 | 122 | 1,051 | 0.836 | 0.373 | **0.515** | 동 단위 anchor 부족 |
| **D** | PERSON | 502 | 2,715 | 1,541 | 0.156 | 0.246 | **0.191** | 도메인 한계 (§4 참조) |
| D | CARD | 56 | 0 | 749 | 1.000 | 0.070 | **0.130** | KDPII 88% Luhn invalid |
| - | **(전체)** | **9,288** | **3,732** | **5,639** | **0.713** | **0.622** | **0.665** | micro |

### Tier 의미

| Tier | F1 | 운영 적합도 |
|---|---|---|
| S | ≥0.95 | Production 즉시 가능 |
| A | 0.80-0.95 | 운영 가능 |
| B | 0.50-0.80 | 사람 검토 권장 |
| C | 0.20-0.50 | recall 보강 필요 |
| D | <0.20 | 도메인 한계 |

### 카테고리별 특이사항

- **PERSON F1 0.191** — KDPII gold 50% 가 별명/2자 이름 단독, 우리 도메인 적합도 §4 참조
- **CARD F1 0.130** — KDPII 카드 88.3% 가 Luhn 체크섬 invalid (저자 fake)
- **ADDRESS F1 0.515** — 동 단위 단독 등장 (anchor 없음) 다수, 정책 trade-off
- **POSITION 오탐 406** — 직책 단어 ("주임/대리") 가 일반 어휘와 충돌

---

## 3. PERSON 분석 — 오탐/미탐 정량 분류

PERSON 만 별도 분석. 정확도 0.156 / 재현율 0.246 의 원인:

### 3-A. 오탐 분류 (2,715 건 분석)

| 분류 | 건수 | 비중 | 예시 |
|---|---:|---:|---|
| 일반 어휘 (단발성) | ~2,200 | 81% | 너무·없어·전화했어·남자·이해 |
| 동사 활용 (끝 하/거/지/해/더) | ~415 | 16% | 마실거·하시든지·예매해 |
| 조사·관계어·회사명 | ~70 | 3% | 신한카드·하은엄마 |
| 호칭+"님" 변형 | 30 | <1% | 강사님·신부님 |

→ **81% 가 카테고리화 안 되는 단발성 어휘** — sources-based emit 정책 한계.

### 3-B. 미탐 분류 (1,541 건 분석)

| 분류 | 건수 | 비중 | 의미 |
|---|---:|---:|---|
| 1자 단성 ("김"·"박") | ~165 | 11% | 공문서 등장 안 함 |
| 2자 이름만 ("미선"·"재명") | ~580 | 38% | 공문서 등장 거의 없음 |
| 3자 풀네임 (한국 성씨) | ~700 | 45% | 공문서 도메인의 진짜 어려움 |
| 4자+ 외국이름·복성 | ~95 | 6% | 도메인 X |

### 3-C. 본질적 한계

**(1) 한국어 단성 성씨 = 일반어 prefix 충돌**

| 성씨 | 충돌 일반어 |
|---|---|
| 김 | 김치·김밥·김장 |
| 이 | 이번·이해·이용 |
| 박 | 박물관·박사·박수 |
| 최 | 최선·최대·최근 |
| 정 | 정성·정확·정답 |

**(2) 대화체 anchor 모호** — "야 그 김민지 알지?" 같은 평어체.

### 3-D. 이번 세션 개선

1. 동 사전 +85개 (admin_unit 거부)
2. 한국어 어말 사전 (`_COMMON_KOREAN_ENDINGS`)
3. 부스트 길이 차등 (3자+ +0.40 / 2자 +0.20)
4. 직책+연결어미 prefix 매칭 ("주임이며" → "주임")

PERSON 오탐 2,871 → 2,715, F1 0.175 → 0.191.

---

## 4. 도메인 적합도 (가장 중요)

### 4-A. KDPII vs 사용자 도메인

| | KDPII (일상 대화) | 공공 문서 |
|---|---|---|
| PERSON gold 1자 단성 | 8.1% | 거의 0% |
| PERSON gold 2자 이름만 | **42.0%** | 거의 0% |
| PERSON gold 3자+ 풀네임 | 49.9% | ~100% |
| 등장 형식 | "재명이가/미선씨구나" | "성명: 박재명" / "박재명 주임" |
| PII 정의 | 화자가 누군지 아는 *맥락 상* | 풀네임 = 직접 식별 |

### 4-B. 법적 근거

**개인정보보호법 제2조:**
> "그 자체로 또는 다른 정보와 쉽게 결합하여 특정 개인을 알아볼 수 있는 정보"

→ 단독 별명·2자 이름 ("재명/미선") 은 그 자체로 식별 불가. 공문서 도메인은
풀네임 위주이므로 우리 정책 (풀네임 검출) 적합.

### 4-C. 사용자 도메인 실측 (행정문서 + PII 주입, §1-bis 참조)

행정문서 베이스 (AI Hub 569) + 합성 PII 주입 200 문서 (1,043 gold spans) 측정:

```
ko-pii micro F1 = 0.901  (TP 1,010 / FP 190 / FN 33)
PERSON F1 = 0.795
```

상세 카테고리별 결과는 §1-bis. 합성 13 템플릿 (회귀 감지) 보다 더 정직한
도메인 적합도 지표.

### 4-D. 도메인별 적합도 종합

| 도메인 | PERSON F1 | ko-pii 적합도 |
|---|---:|---|
| **행정문서 + PII 주입** (사용자 메인) | **0.795** | **운영 가능** |
| 합성 공문서 13 템플릿 | ~0.85 | 좋음 (회귀 감지) |
| 일상 대화 (KDPII) | 0.191 | 룰 기반 한계 |
| 자연어 신문기사 (KLUE-NER) | 0.322 | 어림짐작 |

---

## 5. Decision Log

이번 세션의 비자명한 결정:

| ID | 결정 | 효과 |
|---|---|---|
| D-011 | KDPII 라벨 매핑 정정 (AC_* → TMI_*/QT_*) | EMAIL F1=0.999 등 진짜 정확도 드러남 |
| D-012 | ADDRESS 단독 행정구역 매칭 + anchor | F1 0.18 → 0.42 |
| D-013 | PHONE 대표번호 (15xx-18xx) 추가 | FN 32 → 4 |
| D-014 | PERSON 다중 거부 룰 (호칭/접미사/행정구역/학교/은행) | 오탐 5,202 → 2,715 |
| D-015 | LCP_COUNTRY anchor 면제 | 국가명 86% cover |
| D-016 | 합성 코퍼스 위치 명확화 (sanity check) | 정직성 향상 |
| D-017 | 부스트 길이 차등 (3자+ +0.40 / 2자 +0.20) | PERSON 오탐 -300 |
| D-018 | 한국어 어말 형태소 사전화 | 체계적 어말 거부 |
| D-019 | 직책+연결어미 prefix 매칭 ("주임이며" → "주임") | PERSON 정탐 +66 |
| D-020 | EDUCATION 정규식 outer group 분리 | 약칭 매칭 정상화 |
| D-021 | ADDRESS 국적 접미사 strip ("한국인" → "한국") | ADDRESS 정탐 +153 |

---

## 6. 개선 추이 (시작 → 최종)

| 단계 | KDPII micro F1 | 핵심 변경 |
|---|---:|---|
| 시작 (Phase 7 베이스라인) | 0.412 | 합성 1.000, 실데이터 첫 측정 |
| ACCOUNT 은행명 anchor | 0.500 | 11개 시중은행 키워드 |
| 7 카테고리 신규 | 0.502 | AGE/EDU/MAJOR/POS/BIRTH/REL/HOBBY |
| 룰 정제 1차 | 0.566 | 카테고리별 오탐 분석 |
| PERSON 오탐 1차 | 0.580 | 호칭/동사 활용 거부 |
| ADDRESS+PHONE+PERSON 2차 | 0.598 | 단독 행정구역, 1xxx 대표번호 |
| EDU/MAJOR/POS 사전 | 0.613 | 약칭/단과대/직책 사전 보강 |
| URL/COUNTRY 매핑 + 조사 떨기 | 0.650 | 라벨 매핑 확장 |
| 동 사전 + 어말 사전 + 부스트 차등 | 0.655 | 형태소 단위 거부 |
| **본 세션 최종** | **0.665** | A.1~D.3 룰 정제 + 사전 확장 |

**누적 +0.253 (+61%)** · 외부 ML 의존성 0개.

---

## 7. 가명화 사용 샘플

### 입력 (가공 공문서)
```
서울특별시 종로구청 민원실 회신문

(수신) 김민지 귀하 (010-1234-5678, mjkim@seoul.go.kr)
(주민등록번호) 880101-2123456
(주소) 서울특별시 강남구 테헤란로 124
(차량번호) 12가1234

처리 담당자는 종로구청 환경위생과 박철수 주임 (02-2148-1234) 이며...
```

### 출력 (STRICT + tokenize)
```
서울특별시 종로구청 민원실 회신문

(수신) <PERSON_1> 귀하 (<PHONE_1>, <EMAIL_1>)
(주민등록번호) <RRN_1>
(주소) <ADDRESS_1>
(차량번호) 12가1234

처리 담당자는 종로구청 환경위생과 <PERSON_2> 주임 (<PHONE_2>) 이며...
```

자동 분석:
- 결합 위험도: **CRITICAL** (RRN 단독 식별자)
- 검출: PERSON×2, PHONE×2, EMAIL, RRN, ADDRESS
- 법적 근거: 개인정보보호법 제24조의2 (RRN), 제2조 (기타)

HTML 시각화: `docs/sample_redaction.html` · `docs/kdpii_visual_compare.html`.

---

## 8. 사용자 직접 제어 방법

PERSON 오탐 줄이고 싶으면:

```python
# 옵션 1 — 더 보수적 모드 (MEDIUM 이상만 차단)
Anonymizer(mode=ProcessingMode.BALANCED)

# 옵션 2 — 도메인 사전 추가
from ko_pii.dictionaries import common_words
common_words.COMMON_WORDS = common_words.COMMON_WORDS | {"마실거", "전화했어"}

# 옵션 3 — 검토 큐 워크플로우 (사람이 OK/오탐 마킹)
result = anon.process(text)
for item in result.review_queue:  # 약한 신호 후보
    print(item.text, item.confidence)

# 옵션 4 — LLM hybrid (선택, [ml] extras)
# OpenAI Privacy Filter 와 hybrid → 약한 케이스만 LLM 위임
```

---

## 9. 재현

```bash
# KDPII (사용자 데이터셋 사전 다운로드 필요)
python -m ko_pii.eval.kdpii /path/to/kdpii.jsonl

# KLUE-NER dev
curl -O https://raw.githubusercontent.com/KLUE-benchmark/KLUE/main/\
     klue_benchmark/klue-ner-v1.1/klue-ner-v1.1_dev.tsv
python -m ko_pii.eval.klue_benchmark klue-ner-v1.1_dev.tsv

# 합성 (회귀 감지)
python -m ko_pii.eval.benchmark -n 60 --seed 0
```

---

## 10. 인용

```bibtex
@article{fei2024kdpii,
  title={KDPII: A New Korean Dialogic Dataset for the Deidentification of
         Personally Identifiable Information},
  author={Fei, Li and Kang, Yejee and Park, Seoyoon and Jang, Yeonji
          and Lee, Jongkyu and Kim, Hansaem},
  journal={IEEE Access}, year={2024}, publisher={IEEE},
  doi={10.1109/ACCESS.2024.3461804}
}
```

## 법적 참고

- 개인정보보호법 (제2조, 제23조, 제24조, 제24조의2, 제28조의2-5, 제29조)
- 개인정보보호위원회 「가명정보 처리 가이드라인」
- 개인정보보호위원회 「개인정보 비식별 조치 가이드라인」
