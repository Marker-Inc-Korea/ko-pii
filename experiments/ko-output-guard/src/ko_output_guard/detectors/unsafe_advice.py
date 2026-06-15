"""위험 권고 탐지 — 식약처(MFDS) 도메인 차별점.

발표자료의 실제 사고 사례를 막는다: 독성/공업 물질 섭취 권장, 약물 과다복용,
동일성분 중복 복용. 결정론 룰의 한계상 *명백한 권장*만 잡고(의미적 위험은 Tier-2),
안전 경고('마시지 마세요'/'위험합니다')는 negation 맥락으로 제외해 과탐을 막는다.
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

# 섭취하면 위험한 독성/공업 물질
_TOXIC = (
    r"표백제|락스|메탄올|공업용\s*(?:알코올|알콜)|부동액|살충제|농약|청산가리|아세톤|"
    r"신나|본드|가성소다|양잿물|일산화탄소|포름알데히드|에틸렌\s*글리콜|제초제|쥐약|"
    r"세제|구연산\s*나트륨\s*과다|표백\s*성분|"
    # 식약처 사고 사례 보강: 담배·니코틴, 브로민(염소 제거 식단), 공업·독성 물질
    r"담배\s*(?:진액|농축액)|니코틴\s*(?:원액|농축)?|브로민|브롬화\s*나트륨|소독용\s*에탄올|"
    r"공업용\s*글리세린|메틸알코올|왁스|등유|휘발유|시너|라이터\s*기름|방충제"
)
# 섭취/체내 투입 동사 — 가글·머금·모금 등 우회 표현 포함.
_INGEST = (
    r"(?:드세요|드시(?:면|고|길|는)|마시(?:세요|면|고|는|라)|섭취|복용|먹(?:어|으면|도|는|자)|"
    r"들이키|삼키|가글|머금|입에\s*넣|한?\s*모금|들이부|복용량|drink|swallow|ingest|gargle|consume)"
)

# 안전 경고/금지 맥락 — 이게 근처면 위험 '권장'이 아니라 '경고'이므로 제외.
_SAFE_CTX = re.compile(
    r"마시지\s*마|먹지\s*마|드시지\s*마|섭취\s*(?:하지\s*마|금지)|복용\s*(?:하지\s*마|금지)|"
    r"위험|독성|유독|중독|치명|해롭|안\s*[되돼]|절대\s*안|피하|삼가|하면\s*안|주의"
)

_PATTERNS: list[tuple[re.Pattern[str], Severity, str]] = [
    # 독성/공업 물질 + 섭취 권장
    (re.compile(rf"(?:{_TOXIC})[^.\n]{{0,20}}?{_INGEST}"), Severity.CRITICAL, "toxic_ingestion"),
    # 약물 과다복용 권장 — 배수·다량·여러 + 두자리수 'N정/N알씩'(권장량 초과 수치)
    (re.compile(
        r"(?:권장량[^.\n]{0,6}?(?:초과|넘게|이상|보다\s*많)|두\s*배|세\s*배|[2-9]\s*배|\d{2,}\s*배|"
        r"한꺼번에|여러\s*(?:알|정|개|봉)|\d{2,}\s*(?:정|알|개|봉|캡슐|스푼|티스푼)\s*씩?|"
        r"다량|과량)[^.\n]{0,12}?(?:복용|드세요|드시|먹|섭취)"),
     Severity.HIGH, "overdose"),
    # 동일 성분 중복 복용(아세트아미노펜 계열 등) — 간손상 사례
    (re.compile(
        r"(?:타이레놀|게보린|펜잘|사리돈|아세트아미노펜|이부프로펜)[^.\n]{0,18}?"
        r"(?:함께|같이|동시|추가로|또)[^.\n]{0,18}?"
        r"(?:타이레놀|게보린|펜잘|사리돈|진통제|해열제|감기약|복용|드세요|먹)"),
     Severity.HIGH, "drug_duplication"),
    # 독버섯/야생 섭취 권장
    (re.compile(r"(?:야생|들|산에서\s*캔|이름\s*모르는)\s*버섯[^.\n]{0,15}?"
                r"(?:드세요|드시|먹어도|먹(?:으면\s*)?(?:돼|된다|좋)|식용|안전)"),
     Severity.HIGH, "wild_foraging"),
]


def scan_unsafe_advice(text: str) -> list[Violation]:
    out: list[Violation] = []
    for pat, sev, code in _PATTERNS:
        for m in pat.finditer(text):
            ctx = text[max(0, m.start() - 18):min(len(text), m.end() + 18)]
            if _SAFE_CTX.search(ctx):
                continue  # 안전 경고 맥락 → 위험 권장 아님
            out.append(
                Violation(
                    code=code,
                    category=Category.UNSAFE_ADVICE,
                    severity=sev,
                    reason=f"potentially dangerous recommendation: {code}",
                    start=m.start(),
                    end=m.end(),
                    matched=m.group(0)[:60],
                )
            )
    return out
