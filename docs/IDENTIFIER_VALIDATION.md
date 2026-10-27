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

## English Summary

FRN and RRN have different legacy check digits. Since 1.22.11, FRN detection,
corporate-number disambiguation and format-preserving output use the foreign
digit. Checksums are heuristics, not identity or issuance verification. A
mismatch remains an unverified candidate, not proof that the value is non-PII.
Policy thresholds are unchanged. FRN FPE output can differ from earlier versions;
existing Vault data is not automatically rewritten. Validate downstream output
and your own document distribution before upgrading production pipelines.
