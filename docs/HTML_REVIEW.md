# HTML 원문 검토와 위치별 피드백

`generate_html_report()`는 원문과 처리 결과를 비교하는 **민감한 로컬 검토 화면**입니다.
원문 개인정보를 포함하므로 공개 웹·공유 링크·공개 저장소에 올리지 마세요. 파일과
다운로드에 접근할 수 있는 사용자, 저장 위치·권한·보존 기한은 호출 애플리케이션이 관리합니다.
외부 CSS·JavaScript·모델/API를 불러오지 않습니다.

```python
from ko_pii import Anonymizer, ProcessingMode
from ko_pii.reporting.html_report import generate_html_report

# 합성 예제: 서로 다른 두 위치를 각각 검토합니다.
text = "첫 요청: 880101-1234567 / 두 번째 요청: 880101-1234567"
result = Anonymizer(mode=ProcessingMode.PERMISSIVE).process(text)
html_content = generate_html_report(text, result, document_id="internal-opaque-id")
```

`html_content`를 저장·제공한다면 보호된 저장 위치와 접근 정책을 사용하세요.
`enable_marking=False`는 검토 버튼·JavaScript를 제외하지만 **원문을 제거하지 않습니다**.
정규화, AUDIT, partial과 다른 처리 전략도 원문 표시의 민감성은 같습니다.

## 원문과 결과의 대응

1.27부터 제공한 원문이 모든 탐지 구간의 원문 값과 일치하는지, 치환 전후 좌표와
치환하지 않은 본문이 서로 일치하는지 검사합니다. 같은 PII가 들어 있더라도 다른 문서의
앞뒤 본문과 결과를 섞으면 `ValueError`입니다. 오류에 원문 값은 포함하지 않습니다.

원문과 같은 호출에서 얻은 결과를 함께 전달하세요. 다른 문서의 결과를 재사용하거나
치환 좌표를 버린 과거 결과를 임의로 조합하지 마세요. 직접 만든 결과도 올바른 탐지·
`AppliedSpan` 좌표와 출력이 필요합니다. 이 검사는 구조적 대응이며 작성자 인증이나
보고서 위조 방지·개인정보 제거율 검증은 아닙니다.

## 위치별 표시

REVIEW 항목의 `✓`는 그 **위치의 탐지가 맞음(OK)**, `✗`는 그 **위치가 오탐(FP)**이라는
검토자 판단입니다. 값이 같아도 서로 다른 위치에 별도 판정을 할 수 있습니다. 같은 위치의
판정을 다시 누르면 그 위치만 갱신합니다. 화면의 표시 건수와 선택 상태도 함께 갱신합니다.

원문을 자동으로 수정하거나 검토 표시만으로 가명화·외부 전송을 승인하지 않습니다.
사전·제외 목록·정책을 자동 학습하거나 `ReviewQueue`에 자동 반영하지도 않습니다.
검토 표시가 없는 구간과 미탐 개인정보는 검사했다고 간주하면 안 됩니다.

## 다운로드 형식 v1

1.27부터 `review_marks.json`은 다음 독립 계약을 사용합니다.

```json
{
  "schema_version": 1,
  "contract": "ko-pii-html-review-marks-v1",
  "report_id": "무작위-보고서-ID",
  "scope": "selected_occurrences_only",
  "offset_unit": "python_code_points",
  "source_characters": 46,
  "items": [
    {"finding_id":"finding-0","label":"RRN","source_span":[6,20],"verdict":"OK"},
    {"finding_id":"finding-1","label":"RRN","source_span":[32,46],"verdict":"FP"}
  ]
}
```

- `report_id`는 생성할 때 정하는 UUID4 hex 문자열입니다. 같은 HTML의 다운로드에는 같은
  값이 들어가며 새로 생성한 HTML에는 다른 ID가 붙습니다. 문서 해시·서명·인증은 아닙니다.
- `finding_id`는 해당 보고서 안의 한 탐지 위치를 구분합니다. 다른 보고서의 ID와 합치거나
  값 자체의 영구 ID로 사용하지 마세요. 원본 HTML/내부 작업과의 연결은 호출자가 보존합니다.
- `source_span`은 Python 원문의 문자 인덱스 `[start, end)`입니다. UTF-8 바이트나
  JavaScript UTF-16 인덱스가 아닙니다. 이 예제의 숫자는 위 합성 원문에 대응합니다.
- `items`에는 표시한 위치만 원문 좌표순으로 들어갑니다. 표시하지 않고 다운로드하면
  빈 배열이며, 검토 완료나 안전성 통과를 뜻하지 않습니다.
- 원문 값·토큰·사용자가 입력한 `document_id`는 다운로드에 복사하지 않습니다.
  라벨은 등록된 카테고리 또는 `UNKNOWN`이며 사용자 정의 라벨의 자유 문자열은 내보내지 않습니다.
  라벨·길이·좌표도 내부 정보일 수 있으므로 무조건 공개 가능한 자료는 아닙니다.

기존 HTML의 스크립트는 생성 당시 코드 그대로입니다. 업데이트해도 과거 HTML이 자동으로
변경되지 않습니다. 이전의 버전 없는 `{라벨:원문 또는 토큰: 판정}` 매핑을 읽던 코드는
위의 계약·버전을 확인하고 `items`를 읽도록 변경하세요. 기존 형식은 반복 값의 서로 다른
위치를 복원할 수 없으므로 새 형식으로 무손실 자동 변환하지 않습니다. 필요한 경우 원본
자료로 HTML을 다시 만들고 각 위치를 재검토하세요.
