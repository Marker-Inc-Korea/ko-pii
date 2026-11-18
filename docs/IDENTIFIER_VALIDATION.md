# Identifier checks / 식별번호 검증 범위

ko-pii의 식별번호 검사는 개인정보 후보 탐지를 위한 형식·날짜·검증 숫자 검사입니다.
실제 발급 여부, 본인 확인, 체류 자격 또는 법적 유효성을 확인하는 서비스가 아닙니다.
검증 숫자가 일치해도 우연히 같은 형식인 일반 숫자일 수 있습니다.

## 외국인등록번호 (FRN)

1.22.11부터 레거시 FRN 검증 숫자를 주민등록번호(RRN)와 구분합니다.
앞 12자리의 RRN 가중합 결과에 2를 더하고 10으로 나눈 나머지가 FRN 검증 숫자입니다.
독립적인 대조 근거는 전자정부 표준프레임워크의
[EgovNumberCheckUtil.checkForeignNumber 검증 숫자 계산](https://github.com/eGovFramework/egovframe-common-components/blob/f13bf51f44c6a11b968995768e94fa1d994c8c0a/src/main/java/egovframework/com/utl/fcc/service/EgovNumberCheckUtil.java#L253-L270)
입니다. 해당 구현의 날짜·세기 판정까지 복제한 것이 아닙니다.

- 7번째 숫자 5·6은 1900년대, 7·8은 2000년대로 해석하고 실제 달력 날짜와 미래 날짜를 검사합니다.
- 레거시 검증 숫자가 일치하면 신뢰도 1.0, 일치하지 않으면 0.7로 유지합니다.
  이 값은 규칙의 등급이지 보정된 확률이나 정확도 100%가 아닙니다.
- 실패 근거는 `checksum:unverified`입니다. 번호가 가짜라고 단정하거나 특정 발급 연도로
  해석하지 않습니다. 생년월일에서 발급 시점을 추론할 수 없습니다.
- STRICT/PARANOID는 낮은 신뢰도의 날짜·형식 후보도 처리합니다. BALANCED/PERMISSIVE는
  기본 임계값상 보존할 수 있습니다. AUDIT는 원문을 변경하지 않습니다.
  실제 개인정보 열을 알고 있다면 검증한 `field_labels`/`column_map`을 사용할 수 있습니다.
- 법인번호 체크섬도 동시에 만족하는 후보는 해당 성별 숫자에 맞는 RRN 또는 FRN 계산으로
  구분합니다. 해당 세기의 달력에 없는 날짜나 미래 날짜 때문에 법인 후보까지 사라지지
  않도록 검사합니다. 이것 역시 휴리스틱이며 모든 숫자 충돌의 실제 의미를 판별하지 않습니다.

## 형식 보존 가명화

`strategy="fpe"`의 FRN 출력은 FRN 검증 숫자를 다시 계산합니다. 자릿수·하이픈·성별
숫자 보존을 위한 결정적 매핑이며, 유효한 생년월일·미발급 번호·충돌 없는 식별자를
보장하지 않습니다. 실제 신원 인증이나 외부 시스템의 발급 번호로 사용하지 마세요.
FF1/FF3 암호 구현도 아닙니다. 원문 복원은 별도 Vault를 사용합니다.

1.22.10 이하의 FRN FPE 출력과 새 출력은 달라질 수 있습니다. 과거 출력이나 Vault를
자동 변경하지 않으며, 파생 데이터를 재생성할 때는 별도 버전으로 관리하세요.
Vault의 기존 토큰과 원문 복원 계약은 유지합니다.

## 검사와 적용 판단

고정 합성 벡터, 나머지 11종, 독립 보완 가중치 식으로 만든 1,000개 벡터, 잘못된 입력,
탐지 신뢰도, 법인번호 충돌, JSON·표·CLI·정규화·Vault 복원을 회귀 검사합니다.
이 검사는 계산과 데이터 경로의 일관성을 확인하며, 운영 문서의 탐지율을 증명하지 않습니다.
업무별 평가는 [평가 가이드](DOMAIN_EVALUATION.md)와 해당 조직의 라벨링된 문서로 따로 수행합니다.

## 금융 식별번호의 구분자와 경계

1.22.18은 탐지 조건을 모두 풀어 숫자를 더 많이 가리는 변경이 아니라, 지원 번호의
표기와 다른 필드의 경계를 구분하는 수정입니다.

- 계좌번호는 기존 계좌 키워드/은행명 맥락과 10~16자리 조건을 사용합니다. 하이픈으로
  묶인 번호 또는 완전한 연속 숫자 뒤의 공백·줄바꿈·탭 숫자를 합치지 않습니다.
  `계좌번호 110-123-456789 100000`에서는 번호만 처리하고 뒤 값은 보존합니다.
  공백만으로 구분한 숫자는 계좌 그룹인지 인접 값인지 완전히 구분할 수 없으므로,
  스키마를 아는 입력은 `field_labels`/`column_map`을 우선 사용하세요.
- 카드는 기존 연속 숫자/4자리 그룹 외에 `4-6-5`, `4-6-4`, `4-4-4-4-3`도 지원합니다.
  Luhn·길이·접두사 조건은 그대로입니다. 줄바꿈/탭만으로 그룹을 합치지 않지만,
  명시적 구분자 뒤의 줄바꿈은 래핑으로 허용합니다.
  [American Express의 4-6-5 표기 안내](https://www.americanexpress.com/content/dam/amex/sg/staticassets/merchant/pdf/useful-information/GuidetocheckingCardFaces.pdf)와
  [PayPal의 공개 테스트 번호](https://www.paypalobjects.com/en_GB/vhelp/paypalmanager_help/credit_card_numbers.htm)를
  참고했으며, 테스트 카드 번호와 계산한 합성 번호만 회귀 검사에 사용합니다.
- 사업자번호는 `3-2-5` 그룹 사이의 하이픈·점·한 칸 공백과 구분자 앞뒤 한 칸 공백을
  허용합니다. 줄·탭·두 칸 이상 공백은 연결하지 않습니다. 기존 체크섬과 전체 0 후보
  거부를 유지하며, 점/공백을 사용했다고 해당 숫자가 실제 사업자번호라는 뜻은 아닙니다.

파일의 숫자 줄 경계도 기본 보존합니다. `normalize_for_detection`의 `aggressive=True`는
숫자 줄을 이어 붙일 수 있는 기존 선택 기능이므로, 행/열 경계가 중요한 입력에 사용하지
마세요. 추출 문자열이 바뀌는 파일의 좌표·신규 토큰 순서는 이전 버전과 다를 수 있습니다.
기존 Vault와 과거 출력은 자동 변경하지 않습니다.

### 1.23.1 문맥과 연결 숫자 보완

계좌 키워드/은행명 뒤의 `=`, `"..."`, `“...”`, `「...」`, `(숫자)` 표기와
`번호, 신한은행` 같은 뒤쪽 은행 구분을 인식합니다. 숫자 밖의 구분자와 문구는 보존합니다.
은행 별칭을 다른 단어의 일부에서 찾지 않으며, `신한은행으로부터`, `신한은행에서도` 같은
한정된 조사 표현은 유지합니다. 단독 `우리`·`하나` 같은 약칭 자체의 의미적 모호성은
남아 있습니다. `입금은신한은행110-...`처럼 한글 문장 뒤에 붙은 네 글자 이상 명칭도
유지하지만 짧은 별칭은 단어 경계가 필요합니다. 이 규칙은 금융기관 명칭/계좌의 진위 확인이 아닙니다.

카드는 먼저 연결 숫자 묶음을 읽고 기존의 전체 형식·13~19자리·접두사·Luhn 조건으로
검사합니다. `4111-1111-1111-1111-1234`에서 유효한 16자리 부분만 카드로 주장하지 않습니다.
짧은 1~7자리 그룹을 한두 칸 공백으로 연결한 경우도 묶음 전체를 검사합니다. 반면
공백만으로 별도의 8자리 이상 숫자 필드를 합치지 않으며, 연속 숫자로 적은 카드 두 개나
전화번호 다음의 카드는 각각 처리할 수 있습니다. 기존 `4-6-5`/19자리 형식과 명시적
구분자 뒤 줄바꿈은 유지합니다.

`2026 4111 1111 1111 1111`처럼 짧은 숫자만 연달아 있으면 연도와 카드인지 미지원
연결 번호인지 텍스트만으로 알 수 없습니다. 이 형식은 한 묶음으로 검사하므로 카드의
부분 구간을 추측하지 않습니다. 실제 별도 값이라면 `연도: 2026, 카드: ...`처럼 구분하거나
검증한 구조화 필드 라벨을 사용하세요. 미지원 묶음을 거부한다는 것은 마스킹된다는 뜻이
아닙니다. 업그레이드 전 같은 업무 입력의 최종 출력 잔존과 오탐을 함께 확인해야 합니다.

## English Summary

FRN and RRN have different legacy check digits. Since 1.22.11, FRN detection,
corporate-number disambiguation and format-preserving output use the foreign
digit. Checksums are heuristics, not identity or issuance verification. A
mismatch remains an unverified candidate, not proof that the value is non-PII.
Policy thresholds are unchanged. FRN FPE output can differ from earlier versions;
existing Vault data is not automatically rewritten. Validate downstream output
and your own document distribution before upgrading production pipelines.

Version 1.22.18 fixes account/amount boundaries, recognizes additional formatted
card numbers and single-space/dot-separated business identifiers, and preserves
numeric line boundaries during default file preprocessing. Checksums and existing
prefix/length checks remain heuristics, not an issuance or zero-false-positive
guarantee. Explicit delimiter-plus-newline card wrapping remains supported.
