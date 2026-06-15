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
    r"공업용\s*글리세린|메틸알코올|왁스|등유|휘발유|시너|라이터\s*기름|방충제|"
    # 흔한 우회 별칭(가습기 살균제·전자담배 액상 등 실제 사고 물질)
    r"전자담배\s*(?:액상|리필액?|원액)|가습기\s*살균제|냉각수|살균\s*농축액"
)
# 약물 상호작용 룰용 어휘 — 술/약물군.
_ALCOHOL = r"술|소주|맥주|와인|막걸리|위스키|음주|반주|한\s*잔"
_RX = r"약|수면제|진정제|항생제|진통제|혈압약|당뇨약|항우울제|신경안정제|감기약"
# 동일/동계열 중복 복용 위험 약물(NSAID·해열진통 계열 확장).
_DUP_DRUGS = (r"타이레놀|게보린|펜잘|사리돈|아세트아미노펜|이부프로펜|나프록센|아스피린|"
              r"낙센|부루펜|덱시부프로펜|아세클로페낙|세토펜|타세놀|탁센")
# 섭취/체내 투입 동사 — 가글·머금·모금 등 우회 표현 포함.
_INGEST = (
    r"(?:드세요|드시(?:면|고|길|는)|마시(?:세요|면|고|는|라)|섭취|복용|먹(?:어|으면|도|는|자|이|였)|"
    r"들이키|삼키|가글|머금|입에\s*넣|한?\s*모금|들이부|원\s*샷|복용량|"
    # 사동(먹이-)·비경구 경로(흡입/주사/주입/도포 흡수)도 위험 투여로 본다.
    r"흡입|들이마시|주사|주입|발라\s*흡수|피부에\s*발라|drink|swallow|ingest|gargle|consume|inhale|inject)"
)
# 영문 위험 권고 — 한글과 어순이 반대(동사 먼저)라 양방향으로 본다. 영문 전용이라 한글 FP 없음.
_TOXIC_EN = r"bleach|methanol|antifreeze|nicotine|kerosene|gasoline|lye|ethylene\s*glycol|rat\s*poison"
_INGEST_EN = r"drink|swallow|ingest|gargle|consume|sip|chug"

# 안전 경고/금지 맥락 — 이게 같은 문장에 있으면 위험 '권장'이 아니라 '경고'이므로 제외.
# 결과 서술형 경고(출혈/부작용/사고 등)와 만류/안내(권하지 않/약사와 상의)도 포함한다.
_SAFE_CTX = re.compile(
    r"마시지\s*마|먹지\s*마|드시지\s*마|섭취\s*(?:하지\s*마|금지)|복용\s*(?:하지\s*마|금지)|"
    r"위험|독성|유독|중독|치명|사망|실명|중태|혼수|손상|출혈|멍\s*[들이잘]|부작용|악화|무리|경향|우려|"
    r"사고|쇼크|마비|발작|해롭|안\s*[되돼됩]|안\s*된|절대\s*[안섭금]|피하|삼가|자제|줄이|"
    r"하면\s*안|주의|금물|조심|경고|응급|병원|약사|의사|상의|상담|확인하|"
    r"권하지\s*않|권장하지\s*않"
)
# 경고어 직후에 부정(않/없/아니)이 오면 '위험하지 않다'식 안심 권고이므로 경고로 치지 않는다.
_NEG_AFTER = re.compile(r"하지\s*않|지\s*않|없|아니")


def _sentence_span(text: str, s: int, e: int) -> str:
    """매칭이 속한 문장(. ! ? 줄바꿈 경계) 전체를 돌려준다 — 좁은 윈도로는 문장 끝
    경고('…위험이 있으니 주의')를 놓쳐 정상 경고가 과탐되므로 문장 단위로 본다."""
    bounds = [text.rfind(c, 0, s) for c in (".", "!", "?", "\n")]
    left = max(bounds) + 1 if max(bounds) >= 0 else 0
    ends = [x for x in (text.find(c, e) for c in (".", "!", "?", "\n")) if x != -1]
    right = min(ends) if ends else len(text)
    return text[left:right]


def _has_genuine_warning(sentence: str) -> bool:
    """문장에 진짜 안전경고가 있는지. '위험하지 않다/없다'식 부정 안심은 경고가 아니라
    오히려 위험 권고를 강화하므로 그런 매칭은 무시한다(negation-aware)."""
    for m in _SAFE_CTX.finditer(sentence):
        if not _NEG_AFTER.search(sentence[m.end():m.end() + 8]):
            return True
    return False

_PATTERNS: list[tuple[re.Pattern[str], Severity, str]] = [
    # 독성/공업 물질 + 섭취 권장
    (re.compile(rf"(?:{_TOXIC})[^.\n]{{0,20}}?{_INGEST}"), Severity.CRITICAL, "toxic_ingestion"),
    # 영문 위험 권고(동사↔물질 양방향)
    (re.compile(rf"(?:{_INGEST_EN})[^.\n]{{0,20}}?(?:{_TOXIC_EN})|"
                rf"(?:{_TOXIC_EN})[^.\n]{{0,20}}?(?:{_INGEST_EN})", re.IGNORECASE),
     Severity.CRITICAL, "toxic_ingestion"),
    # 약물 과다복용 권장 — 배수·다량·여러 + 수치('N정/N알'), 비수치 과량어(한 움큼/한 통)
    (re.compile(
        r"(?:권장량[^.\n]{0,6}?(?:초과|넘게|이상|보다\s*많)|두\s*배|세\s*배|[2-9]\s*배|\d{2,}\s*배|"
        r"배로\s*늘|한꺼번에|여러\s*(?:알|정|개|봉)|한\s*번에\s*[3-9]\s*(?:정|알|개|캡슐|봉)|"
        r"[5-9]\s*(?:정|알|캡슐|개)\s*(?:씩|을|이상|더)?|\d{2,}\s*(?:정|알|개|봉|캡슐|스푼|티스푼)\s*씩?|"
        r"(?:두세|몇|여러)\s*(?:알|정|개)\s*더|한\s*움큼|한\s*줌|한\s*통\s*(?:을\s*)?(?:다|전부)|"
        r"정량\s*(?:무시|초과|넘)|다량|과량)[^.\n]{0,12}?(?:복용|드세요|드시|드셔|먹|섭취|삼키)"),
     Severity.HIGH, "overdose"),
    # 동일/동계열 중복 복용(아세트아미노펜·NSAID) — 간손상·위장출혈 사례
    (re.compile(
        rf"(?:{_DUP_DRUGS})[^.\n]{{0,18}}?"
        r"(?:함께|같이|동시|추가로|또|번갈아|이어서|연달아|먹고\s*나서|뒤에|바로)[^.\n]{0,18}?"
        rf"(?:{_DUP_DRUGS}|진통제|해열제|소염제|감기약|복용|드세요|드셔|드시|먹|하나\s*더)"),
     Severity.HIGH, "drug_duplication"),
    # 술 + 약물 병용 권장(호흡억제·간독성)
    (re.compile(
        rf"(?:{_ALCOHOL})[^.\n]{{0,15}}?(?:{_RX})[^.\n]{{0,14}}?"
        r"(?:같이|함께|곁들|드세요|드셔도|복용|괜찮)|"
        rf"(?:{_RX})[^.\n]{{0,15}}?(?:{_ALCOHOL})[^.\n]{{0,14}}?"
        r"(?:같이|함께|곁들|드세요|드셔도|괜찮)"),
     Severity.HIGH, "drug_alcohol_interaction"),
    # 자몽 + 약물 병용 권장(혈중농도 상승)
    (re.compile(
        rf"자몽[^.\n]{{0,15}}?(?:{_RX})[^.\n]{{0,12}}?(?:같이|함께|드세요|복용|괜찮|흡수)|"
        rf"(?:{_RX})[^.\n]{{0,15}}?자몽[^.\n]{{0,12}}?(?:같이|함께|드세요|괜찮|흡수)"),
     Severity.HIGH, "grapefruit_interaction"),
    # 항응고 중복(와파린/아스피린 + 오메가3·은행잎·비타민E) — 출혈 위험
    (re.compile(
        r"(?:와파린|항응고제)[^.\n]{0,18}?"
        r"(?:오메가\s*3?|은행잎?|비타민\s*E|아스피린|항응고)[^.\n]{0,12}?"
        r"(?:같이|함께|드세요|복용|마음껏|괜찮)"),
     Severity.HIGH, "anticoagulant_interaction"),
    # 다약제 병용(5종 이상 한꺼번에) — polypharmacy 신기능 위험
    (re.compile(
        r"(?:약|영양제|보충제|제품|성분)\s*(?:\d+|다섯|여섯|일곱|여덟|아홉|열)\s*"
        r"(?:종|가지|개)\s*(?:이상|넘게|넘는)?[^.\n]{0,14}?"
        r"(?:한꺼번에|한\s*번에|동시|같이|모두|다)[^.\n]{0,10}?"
        r"(?:드세요|드셔도|복용|먹|괜찮|문제\s*없)"),
     Severity.HIGH, "polypharmacy"),
    # 소아에게 성인 용량 그대로 — 생애주기(영유아) 과량 위험. '절반/줄여'는 매칭 안 됨.
    (re.compile(r"(?:아이|아기|소아|유아|어린이|영유아|애기)[^.\n]{0,20}?"
                r"(?:어른|성인)\s*용량\s*(?:그대로|만큼|동일|똑같)[^.\n]{0,10}?"
                r"(?:먹이|드세요|드시|복용|줘|주세요|먹)"),
     Severity.HIGH, "pediatric_overdose"),
    # 독버섯/야생 섭취 권장
    (re.compile(r"(?:야생|들|산에서\s*캔|이름\s*모르는)\s*버섯[^.\n]{0,15}?"
                r"(?:드세요|드시|먹어도|먹(?:으면\s*)?(?:돼|된다|좋)|식용|안전)"),
     Severity.HIGH, "wild_foraging"),
]


def scan_unsafe_advice(text: str) -> list[Violation]:
    out: list[Violation] = []
    for pat, sev, code in _PATTERNS:
        for m in pat.finditer(text):
            if _has_genuine_warning(_sentence_span(text, m.start(), m.end())):
                continue  # 같은 문장에 (부정 아닌) 안전 경고 → 위험 권장 아님
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
