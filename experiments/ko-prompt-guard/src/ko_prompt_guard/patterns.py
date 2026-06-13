"""결정론 룰 레이어 — 한국어 프롬프트 인젝션·탈옥 패턴 사전.

입력은 normalize() 통과 후의 clean text 가정(전각/제로폭/자모/호몰로그가 펴진 상태).
★과탐 방지: '무시/잊어/할머니/필터/탈옥/개발자 모드' 같은 일상어는 (명령형 동사) +
(대상=AI/시스템/지시/규칙/프롬프트) 문맥 단서가 붙을 때만 매칭한다.
"""
from __future__ import annotations

import re

from .result import Category, Severity, Violation

_I = re.IGNORECASE
_H = Severity.HIGH
_M = Severity.MEDIUM

# (compiled, severity) 목록을 카테고리별로.
_P1: list[tuple[re.Pattern[str], Severity]] = [
    (re.compile(
        r"(?:이전|기존|앞서|위(?:에서)?|지금까지|방금)(?:의|\s)*(?:모든\s*)?"
        r"(?:지시|지침|명령|규칙|설정|프롬프트|맥락|대화|내용)"
        r"[^.\n]{0,14}?"
        r"(?:무시|잊어|잊고|잊어버려|버리고|신경\s*쓰지\s*마|신경\s*쓰지\s*말|따르지\s*마)", _I), _H),
    (re.compile(
        r"(?:지시|지침|명령|시스템\s*프롬프트|가이드라인|제약)"
        r"[^.\n]{0,6}?"
        r"(?:무시(?:하고|해|해라|하라|하세요|할)?|잊(?:어버려|어|고)|"
        r"신경\s*쓰지\s*마|신경\s*쓰지\s*말|따르지\s*마)", _I), _H),
    # 대상어 게이트: '상담 내용 무시하고 새로 문의'(정상) 차단, '지시 무시하고 새로'(공격)만.
    (re.compile(
        r"(?:지시|지침|명령|규칙|프롬프트|설정|시스템)[^.\n]{0,6}?"
        r"(?:무시(?:하고|해라|하라|하세요|해)|잊(?:어버려|어|고))\s*"
        r"(?:새(?:로운)?|다음|아래|이제부터|지금부터)", _I), _M),
    # 영어 인젝션(호몰로그/전각 공격이 위장하는 표면형). 'ignore the typos' 류는
    # 대상어(instruction/prompt/rule)가 없어 매칭 안 됨 → 과탐 방지.
    (re.compile(
        r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:the\s+|your\s+)?"
        r"(?:previous|prior|above|earlier|preceding|initial)\s+"
        r"(?:instruction|prompt|rule|message|context|direction)s?", _I), _H),
    (re.compile(
        r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:your\s+|the\s+)?"
        r"(?:instructions|prompts|rules|guidelines|directives)", _I), _H),
    # 'ignore all previous …' 헤더 (대상어가 한글이거나 생략돼도) — ΔRecall 미스 보강.
    # \s* (0+): 분리 합치기로 단어 경계가 사라진 'ignoreall previous'도 커버(splitting).
    (re.compile(r"(?:ignore|disregard|forget|override)\s*all\s*"
                r"(?:the\s*|your\s*)?(?:previous|prior|above|earlier|preceding)", _I), _H),
    # --- round-2 레드팀: 지시 제거/리셋/초기화/덮어쓰기/무효화 ---
    # '설정'은 일상성이 높아(휴대폰/공장/계정 설정 초기화) 대상어에서 분리 — round-4 과탐.
    (re.compile(r"(?:이전|기존|앞선|앞의|위(?:의)?|지금까지|처음|초기)?(?:의|\s)*(?:모든\s*)?"
                r"(?:지시|지침|명령|프롬프트|역할|맥락)"
                r"[^.\n]{0,12}?(?:지우|지워|리셋|초기화|덮어[써쓰]|무효|폐기|취소|날려|"
                r"효력(?:이)?\s*없|효력\s*상실)", _I), _H),
    # '설정'·'규칙' 리셋은 LLM 맥락 한정사(시스템/네/원래…)와 결합할 때만 — 기기·계정
    # 설정 초기화, '영양제 복용 규칙 초기화' 같은 일상 리셋 질문 제외(round-4·5 과탐).
    (re.compile(r"(?:시스템|네|너의|당신의|원래|이전|기존|초기)\s*(?:설정|규칙)"
                r"[^.\n]{0,12}?(?:지우|지워|리셋|초기화|덮어[써쓰]|무효|폐기|취소|날려)", _I), _H),
    (re.compile(r"(?:지시|지침|명령|규칙|프롬프트|설정)"
                r"[^.\n]{0,8}?(?:따를\s*필요\s*없|안\s*따라도\s*(?:돼|된다)|"
                r"무시해도\s*(?:돼|된다)|효력(?:이)?\s*없)", _I), _H),
    # 어순 도치: "무시해 지금까지의 모든 지시를"
    (re.compile(r"(?:무시(?:해|하고|해라|해줘)|잊(?:어|어버려|고))\s*"
                r"(?:지금까지|이전|앞선|위)?(?:의)?\s*(?:모든\s*)?(?:지시|지침|명령|규칙|프롬프트)",
                _I), _H),
    # round-3: 영어 대상어(previous instructions) + 한글 동사(무시/제거) 혼합
    (re.compile(r"(?:previous|prior|above|initial)\s+(?:instructions?|prompts?|rules?)"
                r"[^.\n]{0,8}?(?:무시|잊|제거|지워|버려)", _I), _H),
]

_P2: list[tuple[re.Pattern[str], Severity]] = [
    (re.compile(
        r"(?:시스템\s*프롬프트|시스템\s*메시지|네\s*지침|당신의\s*지침|초기\s*지침|"
        r"원래\s*지침|시스템\s*규칙|숨겨진\s*규칙|내부\s*규칙|설정값)"
        # '시스템 프롬프트 잘 쓰는 법' 같은 작성법 질문은 제외(과탐 방지).
        r"(?:(?!쓰는\s*법|작성|만드|활용|사용법)[^.\n]){0,15}?"
        r"(?:알려(?:줘|주세요|달라)|출력|보여(?:줘|주세요)|말해(?:줘|봐|주세요)|"
        r"공개|복사|그대로|보내(?:줘|봐))", _I), _H),
    (re.compile(
        r"(?:너|당신|네)(?:가|는)?\s*받(?:은|았던)\s*(?:지시|지침|명령|프롬프트|규칙)"
        r"[^.\n]{0,15}?(?:뭐|무엇|알려|출력|보여|말해)", _I), _H),
    (re.compile(
        r"(?:위(?:에서)?|처음에?|맨\s*처음)\s*(?:받은|주어진|설정된|입력된)\s*"
        r"(?:지시|지침|프롬프트|텍스트|내용)"
        r"[^.\n]{0,15}?(?:그대로|전부|다)\s*(?:출력|보여|알려|말해|반복)", _I), _H),
    # --- round-2 레드팀: 숨긴 지침 공개 / 설정 원문 / 처음 설정 역할 ---
    (re.compile(r"(?:숨기[고는]?|숨긴|감춘|비밀(?:의)?|내부)[^.\n]{0,6}?"
                r"(?:지침|규칙|프롬프트|설정|명령)"
                r"[^.\n]{0,10}?(?:공개|알려|보여|출력|말해|읊)", _I), _H),
    (re.compile(r"(?:설정|지침|역할|프롬프트)\s*(?:원문|전문|내용)"
                r"[^.\n]{0,12}?(?:보여|출력|공개|읊|알려|토씨)", _I), _H),
    (re.compile(r"(?:처음|초기|원래|맨\s*처음)에?\s*설정(?:된|한)?\s*(?:역할|지침|프롬프트)"
                r"[^.\n]{0,14}?(?:뭐|무엇|그대로|읊|보여|출력|공개|알려)", _I), _H),
    # 영어/혼용: SYSTEM 프롬프트 / system prompt + 공개 요청 동사
    (re.compile(
        r"(?:시스템|system)\s*(?:프롬프트|prompt|메시지|message)"
        r"(?:(?!쓰는\s*법|작성|만드|활용|사용법)[^.\n]){0,15}?"
        r"(?:알려|출력|보여|말해|공개|복사|그대로|보내|reveal|show|print|repeat|tell)", _I), _H),
    # your / the-system-anchor 필수: 'tell me the rules of chess'·'show me the
    # instructions for assembling'(정상) 제외, 'show me your system prompt'만(round-5 과탐).
    (re.compile(
        r"(?:reveal|show|print|repeat|tell\s+me)\s+(?:me\s+)?"
        r"(?:your\s+(?:system\s+|initial\s+|original\s+)?|the\s+(?:system|initial|original)\s+)"
        r"(?:prompt|instructions?|rules?|guidelines?)", _I), _H),
    # round-3: 첫 메시지 / 받은 설정 / 맨 위 텍스트 노출 유도
    (re.compile(r"(?:첫\s*메시지|첫\s*문장|처음\s*문장|맨\s*위(?:에)?|이\s*대화\s*(?:맨\s*)?위)"
                r"[^.\n]{0,22}?(?:뭐|무엇|보여|적어|출력|복붙|복사|읊|그대로|알려)", _I), _H),
    (re.compile(r"(?:받은|주어진|설정된|네)\s*(?:설정|지침|프롬프트|텍스트|내용|역할|메시지)"
                r"[^.\n]{0,15}?(?:적어|보여|출력|복붙|복사|읊|그대로|알려|공유)", _I), _H),
    # 처음/원래 받은 '지침/프롬프트/설정/역할' 을 읽어/낭독 — 시스템 프롬프트 노출 유도.
    # 대상어를 지침류로 한정해 '받은 메시지 읽어줘'(정상)는 매칭하지 않는다.
    (re.compile(r"(?:처음|맨\s*처음|초기|원래|네가?)\s*받은\s*(?:지침|프롬프트|설정|역할|규칙)"
                r"[^.\n]{0,15}?(?:읽어|낭독|읊|보여|출력|적어|알려)", _I), _H),
]

_P3: list[tuple[re.Pattern[str], Severity]] = [
    # DAN — 탈옥 맥락에서만(단독 'DAN'/이름 '댄(DAN)' 과탐 방지).
    (re.compile(r"(?:너는?\s*|넌\s*|이제\s*)?DAN(?:\s*모드|\s*이?라는|\s*처럼|\s*으?로\s*행동|\s*되어|이야|\s*야)", _I), _H),
    (re.compile(r"두\s*애니씽|do\s*anything\s*now|무엇이든\s*할\s*수\s*있", _I), _H),
    (re.compile(r"(?:제한|규제|필터|검열|제약)\s*(?:이?\s*)?없는\s*"
                r"(?:AI|인공지능|모델|챗봇|GPT|어시스턴트)", _I), _H),
    # 안전장치 해제 — 응답 맥락(답/말/보여) 결합. '스팸 안전 필터 해제 설정' 같은 일반
    # 설정 질문은 제외(과탐 방지).
    (re.compile(r"(?:안전\s*필터|컨텐츠\s*필터|검열|세이프티|가드레?일|안전\s*장치)"
                r"[^.\n]{0,4}?(?:해제|풀어|풀고|꺼|끄고|비활성|우회|뚫|무력화|없애|빼)"
                r"[^.\n]{0,12}?(?:답|말|보여|대답|응답|솔직)", _I), _H),
    # 개발자/관리자 모드 — LLM 대상(너/AI/챗봇) 또는 모드선언일 때만. '게임/안드로이드
    # 개발자 모드'는 일상이라 제외(과탐 방지).
    (re.compile(r"(?:너|당신|넌|AI|인공지능|챗봇|GPT|모델|어시스턴트)[^.\n]{0,12}?"
                r"(?:개발자|[디데]벨[로러롭]퍼|관리자|god|갓)\s*모드", _I), _H),
    # 정상어 '개발자/관리자'는 LLM 페르소나 동사(작동/행동)일 때만 — '에디터 개발자
    # 모드로 진입' 같은 인간 내비게이션(진입/돌입/전환)은 일상이라 제외(round-5 과탐).
    (re.compile(r"(?:개발자|관리자|god|갓)\s*모드"
                r"(?:야|이야|입니다|로\s*(?:작동|행동))", _I), _H),
    # 음차 '디벨로퍼'는 그 자체가 공격 신호 → 전환/진입/돌입까지 포함해도 BLOCK.
    (re.compile(r"[디데]벨[로러롭]퍼\s*모드"
                r"(?:야|이야|입니다|로\s*(?:작동|행동|전환|진입|돌입))", _I), _H),
    # 탈옥 — LLM 대상 결합 또는 요청동사일 때만('게임 탈옥 모드' 등 일상 제외).
    (re.compile(r"(?:AI|인공지능|모델|챗봇|GPT|너|당신|프롬프트)[^.\n]{0,8}?탈옥"
                r"|탈옥\s*(?:시켜|해줘|당해|시도)|탈옥[^.\n]{0,6}?(?:프롬프트|AI|모델|어시스턴트)", _I), _H),
    (re.compile(r"[제젤쟤쟈자]\s*일?\s*브레이크|jail\s*?break|언락\s*모드|unlock\s*mode", _I), _H),
    # 안전/보안 규칙·정책 무력화 — 무력화 동사 결합 시. '장치/필터'는 물리·일반 의미가
    # 강해(자전거 안전장치) 제외하고 규칙/수칙/정책/설정/가드레일만. '안전 규칙 지켜' 제외.
    (re.compile(r"(?:안전|보안)\s*(?:규칙|수칙|정책|설정|가드레?일)"
                r"[^.\n]{0,6}?(?:해제|풀어|풀고|풀\s|우회|뚫|끄고|무력화|없애|비활성|해체|건너뛰)",
                _I), _H),
    # 할머니 익스플로잇 — 서사 유도 + 요청('처럼/해줘')일 때만. 회상('그립네요') 제외.
    (re.compile(r"할머니[^.\n]{0,20}?(?:들려|읽어|알려|불러|얘기)"
                r"[^.\n]{0,15}?(?:처럼\s*(?:말|답|해|얘기)|해\s*줘|알려\s*줘|말해\s*줘|들려\s*줘)", _I), _M),
    (re.compile(r"(?:가상|상상|허구|픽션|소설|시뮬레이션|역할극|롤플레이)"
                r"[^.\n]{0,12}?(?:이?니까|니까|상황|시나리오|설정)"
                r"[^.\n]{0,20}?(?:괜찮|상관\s*없|문제\s*없|가능|허용|돼)", _I), _M),
    # 윤리/안전 규칙 무력화 — '규칙/제약/필터' 단독은 일상('교통 규칙 무시하면')이라 제외.
    (re.compile(r"(?:윤리|도덕|안전)(?:\s*규칙|\s*기준|\s*가이드라인)?"
                r"[^.\n]{0,10}?(?:은|는|이|가)?\s*"
                r"(?:적용\s*(?:안|되지\s*않|할\s*필요\s*없)|무시(?!\s*하지|\s*하면|\s*해도\s*되)"
                r"|신경\s*안\s*써도|없어도\s*돼)",
                _I), _H),
    (re.compile(r"지금부터\s*(?:너|당신|넌|네)\s*(?:는|은)?[^.\n]{0,15}?(?:야|이야|입니다)", _I), _M),
    # --- round-2 레드팀: 신종 탈옥/역할 재정의 표현 ---
    (re.compile(r"(?:탈주|각성|해방|풀려난|깨어난|자각)[^.\n]{0,8}?(?:한|된)?\s*"
                r"(?:자유로운\s*|제약\s*없는\s*)?(?:AI|인공지능|모델|챗봇|GPT|존재)", _I), _H),
    (re.compile(r"무엇이든\s*(?:다\s*)?(?:대답|답변|말|얘기)하는\s*(?:모드|AI|상태|챗봇)", _I), _H),
    (re.compile(r"(?:검열|제약|제한|필터|규제|윤리)\s*(?:도|은|는|없이)?\s*"
                r"(?:받지\s*않|안\s*받|없이|벗어나)[^.\n]{0,10}?(?:답|말|대답|응답|얘기)", _I), _H),
    (re.compile(r"(?:제약|제한|필터|가드레?일|검열|세이프티|안전장치)[^.\n]{0,4}?"
                r"(?:풀고|풀어|풀어서|해제하고|빼고|없애고|꺼|끄고)"
                r"[^.\n]{0,12}?(?:답|말|보여|대답|응답|솔직|다)", _I), _H),
    (re.compile(r"안전[^.\n]{0,5}?(?:같은\s*(?:건|것)|따위)[^.\n]{0,8}?"
                r"(?:신경\s*쓰지\s*(?:마|말)|신경\s*안\s*써도|무시하고|상관\s*없)", _I), _H),
    (re.compile(r"(?:모든\s*)?(?:제약|제한|규칙|한계)(?:에서|을|를|이)?\s*"
                r"(?:벗어나|탈출|풀려|해방)[^.\n]{0,10}?(?:AI|답|말|자유)", _I), _M),
]

_P6: list[tuple[re.Pattern[str], Severity]] = [
    (re.compile(r"(?:지금까지|이제까지|여태까지|위(?:의)?)\s*(?:의|모든)?\s*"
                r"(?:대화|맥락|컨텍스트|내용|메시지|기록)"
                r"[^.\n]{0,15}?(?:전부|모두|다|그대로)\s*(?:출력|보내|보여|알려|복사|반복)", _I), _H),
    (re.compile(r"(?:전체|모든|위)\s*(?:대화|컨텍스트|맥락|히스토리)"
                r"[^.\n]{0,10}?(?:출력|덤프|복사|보내|보여|반복)", _I), _H),
    (re.compile(r"(?:context|컨텍스트|맥락)[^.\n]{0,8}?(?:dump|덤프|leak|유출)", _I), _M),
]

_P7: list[tuple[re.Pattern[str], Severity]] = [
    # 음차 변형 폭넓게: '이그 노어'(공백)/'이그놀'/'익노어', '디/데벨로/러/롭퍼',
    # '제/젤/쟤/쟈일 브레이크' — round-5 레드팀에서 새던 표기 변종 보강.
    (re.compile(r"이그\s*노[어얼올아]|이그\s*놀|익노어", _I), _H),
    (re.compile(r"[디데]벨[로러롭]\s*퍼\s*모드", _I), _H),
    (re.compile(r"[제젤쟤쟈자]\s*일?\s*브레이크", _I), _H),
    (re.compile(r"바이패스|바이페스", _I), _M),
    (re.compile(r"두\s*애니씽\s*나우?|디스리가드|디스레가드|오버라이드", _I), _H),
]

_REGISTRY: list[tuple[Category, list[tuple[re.Pattern[str], Severity]]]] = [
    (Category.INSTRUCTION_OVERRIDE, _P1),
    (Category.PROMPT_LEAK, _P2),
    (Category.JAILBREAK, _P3),
    (Category.EXFILTRATION, _P6),
    (Category.TRANSLITERATION, _P7),
]

# 인코딩 페이로드(원본 텍스트 대상; normalize 가 디코드하지 않으므로 detector 신호).
_ENCODING: list[tuple[re.Pattern[str], Severity]] = [
    # decode-and-run: 해독/복호/수행/처리/적용 까지 + 어순 여유(25). 단 'how-to' 의문문
    # ('base64 디코딩 어떻게 실행해요?')은 학습 질문이라 제외(round-5 과탐).
    (re.compile(r"(?:디코딩|디코드|해독|복호|decode|base64|베이스\s*64)"
                r"(?:(?!어떻게|어케|방법|하나요|할까요|되나요|쓰나요|싶|궁금)[^.\n]){0,25}?"
                r"(?:실행|돌려|수행|처리|적용|run|execute)", _I), _M),
    (re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/])"), _M),
    (re.compile(r"(?:%[0-9A-Fa-f]{2}){4,}"), _M),
    (re.compile(r"(?:\\x[0-9A-Fa-f]{2}){4,}", _I), _M),
]


# 번역/인용 프레이밍 — 영어 injection 표면형이 '명령'이 아니라 '인용 대상'일 때의 단서.
# 한글 명령(이전 지시 무시)은 직접적이라 이 가드 대상 아님(영어 표면형에만 적용).
_TRANSLATION_FRAME = re.compile(
    r"번역|translate|무슨\s*뜻|뜻이\s*(?:뭐|무엇)|뜻을|해석|영어로|한국어로|"
    r"무슨\s*의미|의미(?:가|를)\s*(?:뭐|무엇|알려)", _I
)


def scan(text: str) -> list[Violation]:
    """clean text 에 패턴 매칭. 카테고리별 최고 severity 매치만 보고."""
    out: list[Violation] = []
    for category, pats in _REGISTRY:
        best: Violation | None = None
        for idx, (pat, sev) in enumerate(pats):
            m = pat.search(text)
            if m and (best is None or sev > best.severity):
                best = Violation(
                    code=f"{category.value}#{idx}",
                    category=category,
                    severity=sev,
                    reason=f"{category.value} pattern matched: {m.group(0)[:40]!r}",
                    start=m.start(),
                    end=m.end(),
                    matched=m.group(0),
                )
        # 영어 표면형 injection(ASCII)이 번역/인용 프레이밍과 함께면 인용으로 간주해 제외.
        # 한글 명령이 동반되면 best 가 한글(비ASCII)이라 그대로 잡힌다(우회 방지).
        if (
            best is not None
            and category is Category.INSTRUCTION_OVERRIDE
            and best.matched is not None
            and best.matched.isascii()
            and _TRANSLATION_FRAME.search(text)
        ):
            best = None
        if best is not None:
            out.append(best)
    return out


def scan_encoding(text: str) -> list[Violation]:
    """원본 텍스트의 인코딩 페이로드 탐지(base64/hex/%xx/decode-and-run)."""
    for idx, (pat, sev) in enumerate(_ENCODING):
        m = pat.search(text)
        if m:
            return [Violation(
                code=f"encoding#{idx}",
                category=Category.ENCODING,
                severity=sev,
                reason=f"encoded payload heuristic: {m.group(0)[:40]!r}",
                start=m.start(),
                end=m.end(),
                matched=m.group(0),
            )]
    return []
