# 하이브리드 PII 검출 — 룰(ko-pii) + ML NER

ko-pii는 **결정적 ID(주민·카드·사업자·전화·이메일 등)를 체크섬으로 ~F1 1.0** 잡지만,
**퍼지 카테고리(이름·주소·직책·학력 등)는 약합니다**(KDPII PERSON 0.135 등). 이 약점을
**한국어 토큰분류 NER**로 보완하는 하이브리드를 실험·평가했습니다.

> 설계 원칙: **ko-pii가 결정적 ID 담당(체크섬, ML이 못 이김) · ML이 퍼지 담당.** 교체가 아니라 보완.

## 실험 설정

- **학습 데이터**: KDPII `train`(대화체 40,109문서) + 생성 행정 평가셋의 학습분 1,398문서.
  결정적 ID는 제외하고 **퍼지 20종**(PERSON·ADDRESS·POSITION·EDUCATION·MAJOR·NATIONALITY·
  AGE·DT_BIRTH·HEIGHT·WEIGHT + KDPII 고유 NICKNAME·WORKPLACE 등)만 토큰분류.
- **평가(held-out)**: KDPII `test`(4,891) + 생성 검증셋 540(행정). 동일 매처(`match_forms_overlap`, PML=3).
- **누수 방지**: KDPII **원본 train/test 파티션**을 그대로 사용(재분할 X), 검증 540은 학습에서 제외.
  (KDPII 원본엔 짧은 공통 발화 ~71개가 train/test 중복이나 *PII 보유는 1개* — 사실상 무누수.
  `ko_pii.eval.dataset_integrity.assert_no_text_leakage` 로 빌드타임 검증.)
- **재현**: 데이터는 레포 `data/`(KDPII + 생성셋). 정확한 레시피·명령은 아래 [재현(레시피)](#재현-레시피) 절.

## 베이스 모델 + 하이퍼파라미터 ablation — 퍼지 NER 단독 (seqeval)

| 베이스 | lr·epoch | KDPII fuzzy | 생성 fuzzy | 추론속도 | 판정 |
|---|---|---|---|---|---|
| **klue/roberta-large** (한국어 336M dense) | **2e-5·3ep** | **0.937** | **0.862** | **7.4ms** | ✅ **채택 (포화점)** |
| klue/roberta-large | 2e-5·6ep | 0.935 | 0.844 | 7.4ms | 에폭↑ 효과 없음 |
| klue/roberta-large | 3e-5·6ep | 0.928 | 0.859 | 7.4ms | 고 lr 오히려 ↓ |
| openai/privacy-filter (1.4B MoE) | 1e-4·5ep | 0.633 | 0.437 | 77.5ms | ❌ 학습은 되나 열위 |
| openai/privacy-filter | 2e-5·3ep | 0.138 | 0.209 | 77.5ms | (과소학습 — 아래 ② 참조) |

**① klue는 3 epoch 에서 포화.** 6 epoch·고 lr 모두 3ep(KDPII 0.937 / 생성 0.862)을 못 넘었다 — 추가 학습은
한국어 dense BERT 의 천장에 부딪혀 오히려 과적합 쪽(6ep 생성 0.844, 6ep·3e-5 KDPII 0.928).
**2e-5·3ep 이 정확도·비용 동시 최적 → 프로덕션 레시피.**

**② openai/privacy-filter 의 0.138 은 "구조적 부적합"이 아니라 under-training 이었다(정정).**
초기 lr 2e-5 에선 0.138 에 머물렀으나 **lr 1e-4 로 올리니 KDPII 0.633·생성 0.437 로 ~4.6배 상승** —
모델은 분명히 학습된다. 다만 **1.4B Mixture-of-Experts(층당 128 experts) + 어휘 200K + 131K 롱컨텍스트**
구조라 용량이 다국어 expert 전반에 분산돼, 한국어 특화 **336M dense klue 의 한 forward**를 못 이긴다
(KDPII 0.633 ≪ 0.937). 게다가 한 forward 가 본질적으로 무거워 **추론 10배 느림(77.5 vs 7.4ms/doc)**.
→ *정확도로도 속도로도* 한국어 컴팩트 BERT 가 정답. (lr 1e-4 검증 전의 "부적합" 판정은 과소학습 산물이었음.)

## 전후 비교 — 룰단독 vs 하이브리드 (전체 카테고리, match_forms_overlap)

프로덕션 모델(**klue 2e-5·3ep**, 단독 퍼지 0.937) 기준:

| 평가셋 | ko-pii **룰단독** | **ko-pii + klue 하이브리드** | Δ |
|---|---|---|---|
| KDPII test (대화체) | 0.659 | **0.848** | **+0.189** |
| 생성 540 (행정체) | 0.790 | **0.926** | **+0.136** |

**하이브리드(ko-pii 체크섬ID + klue 퍼지)가 KDPII에서 0.848 → 자체호스팅 Gemma-4-31B(0.796)마저 능가**
(게다가 결정적·온프레미스·체크섬 검증), 생성셋 0.926 → Gemma-31B(0.964) 근접.

## 핵심 매트릭스 — 단독 × 하이브리드 × base/tuned (풀 파이프라인)

| 구성 | KDPII | 생성540 | vs 룰 |
|---|---|---|---|
| ko-pii 룰단독 (기준) | 0.659 | 0.790 | — |
| openai/PF **base** 단독 (zero-shot 퍼지) | 0.264 | 0.451 | — |
| ko-pii + openai/PF **base** (하이브리드) | 0.426 | 0.647 | **−0.23 / −0.14** ❌ |
| ko-pii + openai/PF **tuned**(lr1e-4) (하이브리드) | **0.748** | **0.732** | **+0.09 / −0.06** △ |
| **ko-pii + klue tuned** (하이브리드) | **0.848** | **0.926** | **+0.19 / +0.14** ✅ |

- **base(zero-shot) openai/PF**: 하이브리드가 룰을 **양쪽 다 떨어뜨림** — 나쁜 ML 이 ko-pii 의 *좋은* 퍼지
  검출(예: 생성 ADDRESS 0.966)을 *나쁜* 것으로 교체하기 때문.
- **tuned openai/PF**: 대화체(KDPII)는 룰을 **상회(+0.09)** 하나 행정체(생성)는 **−0.06** 으로 혼조. 퍼지 recall 이
  낮아(생성 fuzzy 0.437) ko-pii 의 강한 룰 ADDRESS 를 교체하면 손해 — **net marginal + 추론 10배 느림**.
- **tuned klue**: 양쪽 모두 큰 폭 개선 — 유일하게 *일관되게* 이득.

> **정정 노트.** 이전 버전은 openai/PF tuned 하이브리드를 "룰 미만 확실"로 *미측정 추정*했으나, 실측 결과
> KDPII 0.748 로 룰(0.659)을 **상회**한다(행정체만 −0.06). 추정이 틀렸고 본 표는 실측치로 교체했다.

## 결론 (중요)

- **좋은 한국어 모델을 튜닝**해야 하이브리드가 *일관되게* 효과(klue: 룰 대비 +0.14~0.19).
- **base(zero-shot) 모델은 역효과** — openai/PF base 하이브리드는 룰보다 **−0.23/−0.14**.
- **부적합으로 보였던 openai/PF 도 제대로 학습하면(lr 1e-4) 대화체에선 이득(+0.09)**, 단 행정체 손해(−0.06)·
  추론 10배 느림으로 **한국어 컴팩트 klue 에 종합 열위** → 불채택. (불채택 사유 = "학습 불가"가 아니라 "열위".)
- 즉 "ML 얹으면 좋아진다"가 아니라 **"제대로 튜닝된 한국어 NER이라야 *일관되게* 좋아진다"**.

## 재현 (레시피)

별도 가중치·스크립트 배포 없이 레포만으로 재현 가능하다. 데이터는 레포 `data/` 를 그대로 쓴다.

- **학습 데이터**: `data/kdpii/{train,valid,test}.json` + `data/generated_eval_large.jsonl` 의 학습분
  (검증 540=`data/generated_eval.jsonl` 은 제외). 라벨은 **퍼지 20종만**(결정적 ID 제외).
- **모델·하이퍼파라미터(프로덕션)**: `klue/roberta-large` · **lr 2e-5 · 3 epoch** · max_len 256 · bs 32 ·
  warmup 0.1 · weight_decay 0.01 · `metric_for_best_model=f1`(epoch 평가). seqeval 로 퍼지 F1 측정.
- **하이브리드 평가**: ko-pii `detect_all` 의 결정적 ID 결과는 그대로 두고 **퍼지만** NER 예측으로 교체,
  동일 매처(`ko_pii.eval.kdpii.match_forms_overlap`, PML=3)로 룰단독 vs 하이브리드 전체 F1 비교.
- **openai/privacy-filter 재현 시 주의**: 반드시 **lr 1e-4 · bf16 · `trust_remote_code`** (lr 2e-5 는 과소학습 → 0.138).

> 토큰분류 학습 루프 자체는 HF `Trainer` + `AutoModelForTokenClassification` 표준 구성이며, 위 설정만
> 그대로 따르면 본 문서의 단독/하이브리드 수치가 재현된다(±0.003 무작위성).

## 모델 공개 (예정)

본 하이브리드의 튜닝 NER(`klue/roberta-large` 기반)은 **추후 공개 예정**입니다. 학습 데이터
라이선스 검토(KDPII·생성셋 재배포 가능 여부)와 도메인 일반화 평가 후 `[classifier]` extra로
가중치를 배포하거나 학습 레시피를 모듈로 제공할 계획입니다. 현재는 **코드·평가·레시피(위 절)만 공개**하며
가중치는 미배포입니다.
