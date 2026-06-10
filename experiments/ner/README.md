# NER 실험 아카이브 — 하이브리드 PII 검출용 토큰분류 모델

ko-pii 하이브리드([`docs/HYBRID_NER.md`](../../docs/HYBRID_NER.md))를 위한 NER 학습·평가
실험 전 과정의 아카이브. **코드(`code/`) · 실행 로그(`runlogs/`) · 원시 결과(`results/`)** 를
그대로 보존한다 — 로그는 진행바/ANSI 코드만 제거한 원본(데이터 구성, 에폭별 loss·F1,
카테고리별 리포트 포함).

> 런별 실측 메타데이터(학습시간·GPU·노드·SLURM 잡ID·하이퍼파라미터):
> [`TRAINING_LOG.md`](TRAINING_LOG.md) (표) · [`runs.json`](runs.json) (기계용).

## 공통 셋업

- **데이터**: KDPII train 40,109 + 생성 행정문서 1,398 = **train 41,507** / valid 5,011 /
  test = KDPII 4,891(대화체) + 생성 540(행정체, held-out). 누수 방지: KDPII 원본 파티션
  보존, 생성 검증 540은 학습 제외.
- **레시피**: lr 2e-5 · 3 epoch · max_len 256 · bs 32 · warmup 0.1 · wd 0.01 ·
  valid F1 기준 best 선택 (변형 실험은 표에 명시).
- **GPU**: RTX6000 1장 (SLURM). 학습 시간: 퍼지 20종 ~15분, 전체 36종 ~29분.

## 실험 목록 (13 runs)

### 학습 (9)

| # | 실험 | 라벨 | 설정 | KDPII | 생성540 | 로그 / 결과 |
|---|---|---|---|---|---|---|
| 1 | klue 3ep (run a) | 퍼지 20 | 2e-5·3ep | 0.934 | 0.846 | `train-klue-3ep-a.log` / `klue-3ep-a.json` |
| 2 | **klue 3ep (run b)** | 퍼지 20 | 2e-5·3ep | **0.937** | **0.862** | `train-klue-3ep-b.log` / `klue-3ep-b.json` |
| 3 | klue 6ep | 퍼지 20 | 2e-5·6ep | 0.935 | 0.844 | `train-klue-6ep.log` / `klue-6ep.json` |
| 4 | klue 6ep 고lr | 퍼지 20 | 3e-5·6ep | 0.928 | 0.859 | `train-klue-6ep-lr3e5.log` / `klue-6ep-lr3e5.json` |
| 5 | openai/PF 저lr | 퍼지 20 | 2e-5·3ep | 0.138 | 0.209 | `train-openai-pf-lr2e5.log` / `openai-pf-lr2e5.json` |
| 6 | openai/PF 고lr | 퍼지 20 | 1e-4·5ep | 0.633 | 0.437 | `train-openai-pf-lr1e4.log` / `openai-pf-lr1e4.json` |
| 7 | **klue 전체학습** | **전체 36** | 2e-5·3ep | **0.950** | **0.882** | `train-klue-all.log` / `klue-all.json` |
| 8 | gemma-4-E2B (디코더 4.6B) | 전체 36 | 5e-5·3ep | 0.353 | 0.701 | `train-gemma4-e2b-all.log` / `gemma4-e2b-all.json` |
| 9 | gemma-4-E2B 고lr | 전체 36 | 1e-4·3ep | 0.351 | 0.673 | `train-gemma4-e2b-all-hilr.log` / `gemma4-e2b-all-hilr.json` |

**#8·#9 (디코더 LLM)**: transformers 에 토큰분류 클래스가 없어 커스텀 헤드
(`code/gemma4_train_ner.py`, 텍스트타워 추출 + linear). 두 lr 모두 valid F1 ~0.33 조기 정체
— 과소학습 아닌 구조적 천장(klue 는 에폭 1에 0.92). 상세: HYBRID_NER.md 확장 평가 절.

수치 = 단독 seqeval F1 (해당 모델의 라벨공간 기준). run a/b 는 동일 설정 반복 — 차이
±0.003~0.016 은 학습 무작위성(재현성 확인용). #7 의 퍼지 서브셋 F1 은 0.936/0.865 로
퍼지 전용 학습(#2)과 동급 — **결정적 ID 라벨을 추가해도 퍼지 성능 손실 없음**.

### 평가 (6)

| # | 평가 | 대상 모델 | 로그 / 결과 |
|---|---|---|---|
| 8 | 하이브리드 전후 비교 (v1) | openai/PF base (zero-shot) | `eval-hybrid-openai-base.log` |
| 9 | 하이브리드 전후 비교 (v1) | openai/PF tuned (1e-4) | `eval-hybrid-openai-tuned.log` |
| 10 | 하이브리드 전후 비교 (v1) | klue 퍼지학습 (#2) | `eval-hybrid-klue-fuzzy.log` |
| 11 | 평가 스위트 (v2, 4모드) | klue **base (무학습)** | `evalsuite-klue-base.{log,json}` |
| 12 | 평가 스위트 (v2, 4모드) | klue 퍼지학습 (#2) | `evalsuite-klue-fuzzy.{log,json}` |
| 13 | 평가 스위트 (v2, 4모드) | klue 전체학습 (#7) | `evalsuite-klue-all.{log,json}` |
| 14 | **3안: ML+룰 체크섬 검증** | klue 전체학습 (#7) | `verified-eval.log` / `verified-klue-all.json` |
| 15 | 체크섬 프로브 (정성) | 룰 vs klue 전체학습 | `checksum-probe.log` |
| 16 | 마스킹 시연 (탐지→후처리) | 룰 vs klue 전체학습 | `mask-demo.log` |

**3안 (#14)**: ML단독 0.949/0.943 → +룰검증 0.919(−0.030)/0.929(−0.014). 벤치마크에선
손해지만 원인은 **gold ID 가 대부분 가짜 번호**(아래 캐비엇) — gold 가 95% 유효한 생성540
CARD 에선 FP 7 제거 vs TP 2 손실로 **이득**. RRN 은 2020-10 무작위화로 검증 제외.

## 채점 매트릭스 — 전체 카테고리, match_forms_overlap (프로토콜 v2)

룰단독(ko-pii) 기준선: **KDPII 0.659 / 생성540 0.790**

| 모델 (KDPII / 생성540) | ML단독 | 하이브리드(룰ID+ML퍼지) | 유니온(룰∪ML) |
|---|---|---|---|
| klue base (무학습) | 0.002 / 0.005 | 0.059 / 0.110 | 0.108 / 0.195 |
| klue 퍼지학습 (20종) | 0.685 / 0.661 | **0.904 / 0.927** | 0.799 / 0.863 |
| klue 전체학습 (36종) | **0.949 / 0.943** | 0.898 / 0.924 | 0.847 / 0.875 |

핵심 관찰 (상세 분석: [`docs/HYBRID_NER.md`](../../docs/HYBRID_NER.md)):

1. **전체학습 ML단독이 전 구성 최고** — 단, 인도메인 벤치마크 기준이며 체크섬 검증
   불가(무효 번호 구분 못함)·OOD 일반화는 별개 (아래 캐비엇).
2. **퍼지학습 모델은 하이브리드가 최적** — 역할 분담(룰=ID, ML=퍼지)이 유효.
3. **유니온은 항상 하이브리드 이하** — 양쪽 FP 가 합산됨. 단 recall 은 모드 중 최대
   (전체학습 유니온: KDPII 0.937 / 생성 0.965) → 보수적 마스킹 용도.
4. **무학습 base 는 어느 모드든 룰을 파괴** (0.659→0.059) — 하이브리드는 ML 품질에
   하방이 뚫려 있음. openai/PF base(−0.23)와 일관된 결론.

## 채점 프로토콜 v1 vs v2

- **v1** (`hybrid_eval.py`, 실험 #8~10): ML 예측을 공유 퍼지 10종으로 필터, gold
  라벨공간 보정 없음. KDPII gold 엔 NATIONALITY 라벨이 없는데(LCP_COUNTRY→ADDRESS)
  ML 의 NATIONALITY 예측을 FP 로 계산 → klue 하이브리드 KDPII **0.848**.
- **v2** (`eval_suite.py`, 실험 #11~13): ML 예측을 **데이터셋 gold 라벨공간으로 한정**
  + span 정규화(strip, PERSON<3자 제외) → 같은 모델·같은 데이터가 KDPII **0.904**.
  생성540 은 0.926→0.927 로 불변(라벨공간 차이가 없으므로) — 차이의 원인이
  라벨공간 보정임을 검증.

## 캐비엇 (정직 노트)

- **벤치마크 gold ID 대부분이 "형식만 맞는 가짜 번호"**: 체크섬 유효율 — KDPII CARD 9%(7/78),
  생성540 RRN 15%·BUSINESS_REG 13%·CORP_REG 19% (CARD 만 95%). 룰의 사업자 recall 0.129 가
  유효율 13%와 일치 — 룰은 실존 불가 번호를 거부(설계)했는데 벤치마크가 FN 으로 처벌.
  **ML단독 우위의 일부는 가짜 번호 분포를 학습한 합성 아티팩트.**
- 생성540 의 ID 패턴은 학습에 쓴 1,398 문서와 같은 생성기에서 나옴 → 전체학습 모델의
  ID 검출은 **인분포 평가**. ML 은 체크섬 진위 판정이 불가(프로브 #15: 무효 카드도 검출).
  단 RRN 은 2020-10 뒷자리 무작위화로 룰도 체크섬을 신뢰도 신호로만 사용.
- KDPII test 는 KDPII train 과 같은 코퍼스의 held-out → 도메인 외 일반화는 별도 평가
  필요 (`docs/HYBRID_NER.md` 모델 공개 선행 조건과 동일).

## 재현

```bash
# 퍼지 20종 (프로덕션 레시피)
python code/train_ner.py --base klue/roberta-large --out out/ner_fuzzy

# 전체 36종 (결정적 ID 포함)
python code/train_ner.py --base klue/roberta-large --out out/ner_all --all-labels

# 평가 스위트 (단독 seqeval + 룰/ML단독/하이브리드/유니온)
python code/eval_suite.py out/ner_fuzzy/final     # 또는 base-fuzzy (무학습 베이스라인)
```

sbatch(`code/*.sbatch`)는 SLURM + venv tarball staging 환경용 — 일반 환경에선 위
python 명령을 직접 실행하면 된다 (데이터 경로는 스크립트 상단 상수, 레포 `data/` 기준).
