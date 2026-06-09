# generated_eval_large.jsonl — 확장 합성 PII 평가셋 (견고성 대조용)

`generated_eval.jsonl`(540, 감사 완료)에 **Gemma-4-31B 생성 1,398문서**를 더한 **1,938문서**
확장셋. ko-pii 점수의 안정성을 더 큰·다양한 셋에서 확인하기 위한 용도.

| 항목 | 값 |
|---|---|
| 문서 수 | 1,938 (540 검증 + 1,398 신규) |
| gold span | ~16,900 |
| 형식 | `generated_eval.jsonl`과 동일 (`{text, pii:[{type,text}], domain}`) |

## 품질 수준 (중요)

- **540분**: 2단계 검증(형식 + LLM 적대적 감사) 완료, gold 98.8% 정확. → 정식 벤치마크.
- **1,398분**: Gemma-4-31B 자동 생성 + **형식검증만**(gold가 본문에 글자그대로 존재, 16자리 카드 Luhn 보정).
  라벨 정확도는 **수동 감사하지 않음** → 540보다 노이즈 있음.

## 사용 주의

- **LLM(Gemma 계열) 평가 금지** — 1,398분의 gold를 Gemma-31B가 생성했으므로 Gemma를 채점하면
  **자기 gold 순환**이라 점수가 부풀려진다. 독립 시스템(ko-pii·Presidio·openai/PF)만 공정.
- 정식 성능 수치는 `generated_eval.jsonl`(540, 감사본) 기준. 본 확장셋은 **안정성 대조**로만 사용.

## 측정 (독립 시스템, 동일 매처 `match_forms_overlap`, PML=3)

| 시스템 | F1 (1,938) | F1 (540) |
|---|---|---|
| ko-pii | 0.825 | 0.790 |
| openai/privacy-filter | 0.538 | 0.451 |
| Presidio | 0.478 | 0.483 |

3.6× 큰 셋에서도 ko-pii 우위 유지. 자세한 논의는 `docs/BENCHMARK.md` §3c.
