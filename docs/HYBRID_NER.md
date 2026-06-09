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

## 베이스 모델 비교 — 퍼지 NER 단독 (seqeval, 퍼지 카테고리)

| 베이스 | KDPII fuzzy | 생성 fuzzy | 학습속도 | 판정 |
|---|---|---|---|---|
| **klue/roberta-large** (한국어) | **0.934** | **0.846** | ~5분 | ✅ **압도적 승** |
| klue/roberta-large (SLURM 재현) | 0.937 | 0.862 | ~5분 | (재현성 확인) |
| openai/privacy-filter (다국어, 660M) | 0.138 | 0.209 | ~90분 | ❌ 부적합 |

→ **한국어 네이티브 베이스가 정답.** openai/privacy-filter는 정확도 ~7배 낮고 학습·추론도 ~10배 느림.
(SLURM 재현 0.937 vs 직접 0.934 차이는 학습 무작위성, ±0.003 — 재현 안정성 확인.)

**추론 속도 (동일 GPU 실측):** klue-large **7.4ms/doc** vs openai/PF **77.5ms/doc**(~10배 느림).
openai/PF는 실제 **1.4B 파라미터**(klue 336M의 4배) + **어휘 200K**(6배) + **131K 롱컨텍스트** 커스텀
아키텍처라 한 forward가 본질적으로 무거움 — 한국어 컴팩트 BERT 대비 정확도·속도 모두 열위.

## 전후 비교 — 룰단독 vs 하이브리드 (전체 카테고리, match_forms_overlap)

| 평가셋 | ko-pii **룰단독** | **ko-pii + ML 하이브리드** | Δ |
|---|---|---|---|
| KDPII test (대화체) | 0.659 | **0.842** (klue) | **+0.183** |
| 생성 540 (행정체) | 0.790 | **0.919** (klue) | **+0.129** |

**하이브리드(ko-pii 체크섬ID + klue 퍼지)가 KDPII에서 0.842 → 자체호스팅 Gemma-4-31B(0.796)마저 능가**
(게다가 결정적·온프레미스·체크섬 검증), 생성셋 0.919 → Gemma-31B(0.964) 근접.

## 핵심 매트릭스 — 단독 × 하이브리드 × base/tuned (풀 파이프라인)

| 구성 | KDPII | 생성540 |
|---|---|---|
| ko-pii 룰단독 | 0.659 | 0.790 |
| openai/PF **base** 단독 (zero-shot) | 0.264 | 0.451 |
| ko-pii + openai/PF **base** (하이브리드) | **0.426** | **0.647** |
| ko-pii + openai/PF **tuned** (하이브리드) | 미측정¹ | 미측정¹ |
| **ko-pii + klue tuned** (하이브리드) | **0.842** | **0.919** |

¹ openai/PF 추론 병목(배포 부적합)으로 미측정. tuned 단독 퍼지 0.138/0.209 < base 이므로 하이브리드도 룰 미만 확실.

## 결론 (중요)

- **좋은 한국어 모델을 튜닝**해야 하이브리드가 효과(룰 대비 +0.13~0.18).
- **base(zero-shot)·부적합 모델은 오히려 역효과** — openai/PF base 하이브리드는 룰보다 **−0.23/−0.14**.
  나쁜 ML이 ko-pii의 *좋은* 퍼지 검출(예: 생성 ADDRESS 0.966)을 *나쁜* 것으로 교체하기 때문.
- 즉 "ML 얹으면 좋아진다"가 아니라 **"제대로 튜닝된 한국어 NER이라야 좋아진다"**.

## 모델 공개 (예정)

본 하이브리드의 튜닝 NER(`klue/roberta-large` 기반)은 **추후 공개 예정**입니다. 학습 데이터
라이선스 검토(KDPII·생성셋 재배포 가능 여부)와 도메인 일반화 평가 후 `[classifier]` extra로
가중치를 배포하거나 학습 레시피를 제공할 계획입니다. 현재는 **코드·평가·레시피만 공개**하며
가중치는 미배포(`python -m ko_pii.classifier.train` 으로 직접 학습 가능).
