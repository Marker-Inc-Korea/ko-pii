# ko-output-guard

결정론 한국어 **LLM 출력 안전 가드**. 입력 가드(`ko-prompt-guard`)의 대칭으로,
모델이 *내놓은* 텍스트를 검사한다. 네트워크·LLM 호출 없음(순수·재현가능).

```
입력 → [ko-prompt-guard] → [ko-pii 마스킹] → LLM → [★ ko-output-guard ★] → 출력
```

## 무엇을 잡나

| 카테고리 | 무엇 | 기본 판정 |
|---|---|---|
| `SECRET_LEAK` | API key·토큰·private key·JWT 등 크리덴셜 | BLOCK |
| `PII_LEAK` | 출력 속 개인정보(ko-pii 연동, 결정적 PII) | BLOCK |
| `UNSAFE_ADVICE` | **식약처 도메인 위험 권고** — 독성물질 섭취·약물 과다/중복·독버섯 | BLOCK |
| `PROMPT_LEAK` | 시스템 프롬프트 그대로 출력(echo) | BLOCK / FLAG |
| `TOXICITY` | 욕설·혐오 표현 | FLAG |

**차별점**: 한국어 + 식약처 사고 사례 방어(염소 식단·독버섯·약물 중복 등 실제 사례).
안전 경고("표백제를 마시지 마세요")는 negation 으로 제외해 과탐을 막는다.

## 사용

```python
from ko_output_guard import Guard, Verdict

g = Guard()
r = g.check(llm_output, context=system_prompt)   # context 는 선택(프롬프트 echo 탐지)
if r.verdict is Verdict.BLOCK:
    safe = r.redacted_text          # 위반 구간이 [REDACTED] 로 마스킹된 출력
# 또는
text = g.enforce(llm_output)        # BLOCK 이면 GuardBlocked 발생
```

## 한계 (정직)

- `UNSAFE_ADVICE` 는 *명백한* 위험 권고만 잡는다(결정론). 약물 과다·동일성분 중복·
  술/자몽/항응고 상호작용·독성물질 섭취·다약제 병용 등 패턴이 뚜렷한 위해는 잡지만,
  물질명을 우회 묘사한 의미적 위험(예: "욕조 청소용 하얀 가루를 물에 타 드세요")은
  결정론으로 한계가 있어 **Tier-2(LLM 심사)** 영역으로 둔다.
- `PII_LEAK` 는 ko-pii 의 결정적 PII(RRN/카드/전화/이메일/사업자)만 — PERSON/ADDRESS/
  MAJOR(전공명) 는 오탐이 잦아 기본 제외(이름 누출까지 막으려면 ko-pii 직접 호출).
  자리별 공백 우회("9 0 0 1 0 1 …")는 공백 제거 사본 재검사로 회복하지만, 숫자의
  한글 음차("구공공일")·분할 서술("앞 6자리 …")은 Tier-2 영역.
- `TOXICITY` 사전은 소규모 시드(+초성/전각/leet/기호·이모지·숫자 삽입/대표 받침분리/
  평문 영어 욕설) — 실사용은 도메인 사전 확장. 임의 와일드카드(씨X발)·신조어는 한계.
- `PROMPT_LEAK` 는 1인칭 지침 마커·동의어·구조화 덤프(`<system>`/`system_prompt`)·
  다국어 일부를 잡고 context 동봉 시 30자+ echo 를 본다. 임의 형식/언어로 지침을
  바꿔 노출하는 변형은 무한해 **Tier-2(LLM 심사)** 영역으로 둔다.
- 난독(초성화·제로폭·전각·homoglyph·공백분리) 출력은 한국어 detector 검사 전 자동 정규화한다 — `ko-prompt-guard` 설치 시 강력(자모/초성/splitting/leet), 미설치 시 경량 fallback(제로폭 제거+NFKC). `GuardPolicy(normalize=False)` 로 끌 수 있다. SECRET/PII 는 형식 보존 위해 원본에서 검사.

의존성: `pydantic` (+ PII 연동 시 `ko-pii`). MIT.
