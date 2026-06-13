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
        r"(?:지시|지침|명령|규칙|시스템\s*프롬프트|가이드라인|제약)"
        r"[^.\n]{0,6}?"
        r"(?:무시(?:하고|해|해라|하라|하세요|할)?|잊(?:어버려|어|고)|"
        r"신경\s*쓰지\s*마|신경\s*쓰지\s*말|따르지\s*마)", _I), _H),
    (re.compile(
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
]

_P2: list[tuple[re.Pattern[str], Severity]] = [
    (re.compile(
        r"(?:시스템\s*프롬프트|시스템\s*메시지|네\s*지침|당신의\s*지침|초기\s*지침|"
        r"원래\s*지침|시스템\s*규칙|숨겨진\s*규칙|내부\s*규칙|설정값)"
        r"[^.\n]{0,15}?"
        r"(?:알려(?:줘|주세요|달라)|출력|보여(?:줘|주세요)|말해(?:줘|봐|주세요)|"
        r"공개|복사|그대로|보내(?:줘|봐))", _I), _H),
    (re.compile(
        r"(?:너|당신|네)(?:가|는)?\s*받(?:은|았던)\s*(?:지시|지침|명령|프롬프트|규칙)"
        r"[^.\n]{0,15}?(?:뭐|무엇|알려|출력|보여|말해)", _I), _H),
    (re.compile(
        r"(?:위(?:에서)?|처음에?|맨\s*처음)\s*(?:받은|주어진|설정된|입력된)\s*"
        r"(?:지시|지침|프롬프트|텍스트|내용)"
        r"[^.\n]{0,15}?(?:그대로|전부|다)\s*(?:출력|보여|알려|말해|반복)", _I), _H),
    # 영어/혼용: SYSTEM 프롬프트 / system prompt + 공개 요청 동사
    (re.compile(
        r"(?:시스템|system)\s*(?:프롬프트|prompt|메시지|message)"
        r"[^.\n]{0,15}?"
        r"(?:알려|출력|보여|말해|공개|복사|그대로|보내|reveal|show|print|repeat|tell)", _I), _H),
    (re.compile(
        r"(?:reveal|show|print|repeat|tell\s+me)\s+(?:me\s+)?(?:your\s+|the\s+)?"
        r"(?:system\s+|initial\s+|original\s+)?(?:prompt|instructions?|rules?)", _I), _H),
]

_P3: list[tuple[re.Pattern[str], Severity]] = [
    (re.compile(r"(?<![A-Za-z가-힣])DAN(?![A-Za-z])\b", _I), _H),
    (re.compile(r"두\s*애니씽|do\s*anything\s*now|무엇이든\s*할\s*수\s*있", _I), _H),
    (re.compile(r"(?:제한|규제|필터|검열|제약)\s*(?:이?\s*)?없는\s*"
                r"(?:AI|인공지능|모델|챗봇|GPT|어시스턴트)", _I), _H),
    (re.compile(r"(?:안전\s*필터|컨텐츠\s*필터|검열|세이프티|가드레?일|안전\s*장치|안전\s*규칙)"
                r"[^.\n]{0,6}?(?:해제|풀어|꺼|끄고|비활성|우회|뚫|무력화|없애)", _I), _H),
    (re.compile(r"(?:개발자\s*모드|디벨로퍼\s*모드|developer\s*mode|관리자\s*모드|god\s*mode|갓\s*모드)"
                r"[^.\n]{0,10}?(?:활성|enabled|켜|on|진입|전환|해제|돌입|들어가)", _I), _H),
    (re.compile(r"(?:개발자|관리자)\s*모드(?:야|이야|입니다|로\s*작동|로\s*행동)", _I), _H),
    (re.compile(r"(?:AI|인공지능|모델|챗봇|GPT|너|당신|프롬프트)[^.\n]{0,8}?탈옥"
                r"|탈옥[^.\n]{0,8}?(?:모드|프롬프트|시켜|해줘|당해|시도)", _I), _H),
    (re.compile(r"제일\s*브레이크|제일브레이크|jail\s*?break|언락\s*모드|unlock\s*mode", _I), _H),
    (re.compile(r"(?:죽은\s*)?할머니(?:가|는|께서)?[^.\n]{0,20}?"
                r"(?:들려|읽어|알려|말해|불러|알려주던|얘기해)", _I), _M),
    (re.compile(r"(?:가상|상상|허구|픽션|소설|시뮬레이션|역할극|롤플레이)"
                r"[^.\n]{0,12}?(?:이?니까|니까|상황|시나리오|설정)"
                r"[^.\n]{0,20}?(?:괜찮|상관\s*없|문제\s*없|가능|허용|돼)", _I), _M),
    (re.compile(r"(?:윤리|도덕|안전|규칙|제약|필터)(?:\s*규칙|\s*기준|\s*가이드라인)?"
                r"[^.\n]{0,10}?(?:은|는|이|가)?\s*"
                r"(?:적용\s*(?:안|되지\s*않|할\s*필요\s*없)|무시(?!\s*하지|\s*하면\s*안|\s*하지\s*마)"
                r"|신경\s*안\s*써도|없어도\s*돼|상관\s*없)",
                _I), _H),
    (re.compile(r"지금부터\s*(?:너|당신|넌|네)\s*(?:는|은)?[^.\n]{0,15}?(?:야|이야|입니다)", _I), _M),
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
    (re.compile(r"이그노어\s*(?:올|얼|all)?\s*(?:프리비어스|프리비우스|프리비|previous)?", _I), _H),
    (re.compile(r"시스템\s*프롬프트", _I), _M),
    (re.compile(r"디벨로퍼\s*모드|디벨롭퍼\s*모드", _I), _H),
    (re.compile(r"제일\s*브레이크|제일브레이크|쟤일브레이크", _I), _H),
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
    (re.compile(r"(?:디코딩|디코드|decode|base64|베이스\s*64)[^.\n]{0,15}?"
                r"(?:실행|돌려|run|execute)", _I), _M),
    (re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/])"), _M),
    (re.compile(r"(?:%[0-9A-Fa-f]{2}){4,}"), _M),
    (re.compile(r"(?:\\x[0-9A-Fa-f]{2}){4,}", _I), _M),
]


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
