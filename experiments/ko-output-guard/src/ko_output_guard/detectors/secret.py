"""크리덴셜/시크릿 누출 탐지 — LLM 이 출력에 API key·토큰·private key 를 뱉는 경우.

알려진 고-엔트로피 토큰 형식(gitleaks/detect-secrets 계열)을 정규식으로 잡는다.
형식이 확정적인 클라우드/서비스 키는 CRITICAL, 범용 'key=...' 할당은 오탐 여지가
있어 MEDIUM. 모두 원본 텍스트 대상(normalize 불필요 — 토큰은 ASCII).
"""
from __future__ import annotations

import re

from ..result import Category, Severity, Violation

# (code, compiled, severity)
_PATTERNS: list[tuple[str, re.Pattern[str], Severity]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), Severity.CRITICAL),
    ("aws_secret", re.compile(r"(?i)aws.{0,20}?(?:secret|key).{0,5}['\"=:\s]([A-Za-z0-9/+]{40})\b"),
     Severity.CRITICAL),
    ("github_pat", re.compile(r"\bgh[pos]_[0-9A-Za-z]{36}\b"), Severity.CRITICAL),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{59,}\b"), Severity.CRITICAL),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), Severity.CRITICAL),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), Severity.CRITICAL),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), Severity.CRITICAL),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), Severity.CRITICAL),
    ("stripe_key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{24,}\b"), Severity.CRITICAL),
    ("private_key_block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA |ENCRYPTED )?PRIVATE KEY-----"),
     Severity.CRITICAL),
    ("jwt",
     re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
     Severity.HIGH),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9_\-.=]{20,}", re.IGNORECASE), Severity.HIGH),
    # 범용 'api_key = "..."' 류 — 오탐 여지(설명용 placeholder)라 MEDIUM.
    ("generic_secret_assignment",
     re.compile(
         r"(?i)(?:api[_-]?key|secret|token|password|passwd|access[_-]?key)"
         r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})"
     ),
     Severity.MEDIUM),
    # --- 연결 문자열 / 추가 서비스 토큰 형식(red-team 발견) ---
    # scheme://user:PASSWORD@host — postgres/mysql/mongodb/redis/amqp 등. group(1)=password.
    ("db_connection_string",
     re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@]*:([^/\s:@]{6,})@"), Severity.HIGH),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), Severity.CRITICAL),
    ("azure_storage_key",
     re.compile(r"AccountKey=([A-Za-z0-9+/]{40,}={0,2})"), Severity.CRITICAL),
    ("azure_ad_secret", re.compile(r"\b[A-Za-z0-9~._-]{2,4}~[A-Za-z0-9~._-]{30,}\b"), Severity.HIGH),
    ("sendgrid_key",
     re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"), Severity.CRITICAL),
    ("discord_token",
     re.compile(r"\b[MNO][A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"),
     Severity.HIGH),
    ("slack_webhook",
     re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"), Severity.HIGH),
    # prefix 가 고유한 서비스 토큰 형식(gitleaks/detect-secrets 계열) — 저-FP.
    ("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b"), Severity.HIGH),
    ("gitlab_pat", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), Severity.HIGH),
    ("digitalocean_pat", re.compile(r"\bdop_v1_[a-f0-9]{64}\b"), Severity.HIGH),
    ("shopify_token", re.compile(r"\bshpat_[a-fA-F0-9]{32}\b"), Severity.HIGH),
    ("pypi_token", re.compile(r"\bpypi-AgEI[A-Za-z0-9_-]{50,}"), Severity.CRITICAL),
    ("telegram_bot_token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33,}\b"), Severity.HIGH),
    ("mailgun_key", re.compile(r"\bkey-[0-9a-zA-Z]{32}\b"), Severity.HIGH),
    ("square_token", re.compile(r"\bsq0(?:atp|csp)-[A-Za-z0-9_-]{22,}\b"), Severity.HIGH),
    # JDBC/쿼리형 비밀번호(scheme://user:pass@ 의 sibling) — group(1)=password.
    ("jdbc_password",
     re.compile(r"(?i)jdbc:[^\s]*[?;&]password=([^\s&;]{6,})"), Severity.HIGH),
    # base64 로 감싼 키 누출 유도 — '디코드하면 키/토큰' 프레이밍 + 실제 base64 blob 필수.
    ("base64_wrapped_secret",
     re.compile(r"(?i)(?:base64[^.\n]{0,18}?(?:디코드|디코딩|decode)[^.\n]{0,18}?"
                r"(?:키|토큰|비밀|시크릿|secret|key|password)[^.\n]{0,20}?[A-Za-z0-9+/]{24,}={0,2})|"
                r"(?:키|토큰|비밀번호|시크릿)\s*:?\s*[A-Za-z0-9+/]{20,}={0,2}"),
     Severity.MEDIUM),
]

# 명백한 placeholder/예시는 generic 오탐에서 제외. 'my'는 단독이 진짜 비번('MyP4ss')을
# 가리지 않도록 'my_key' 류로만, 'password/passwd'(문서용 값)는 추가.
_PLACEHOLDER = re.compile(
    r"(?i)^(?:your|the|example|placeholder|xxx+|<.*>|\.\.\.|insert|todo|changeme|"
    r"abc123|0+|1+|test|dummy|sample|redacted|password|passwd|replace|change_?me|"
    r"my[_-](?:key|token|secret|pass)|\*+)",
)


def scan_secrets(text: str) -> list[Violation]:
    out: list[Violation] = []
    seen: set[tuple[int, int]] = set()
    for code, pat, sev in _PATTERNS:
        for m in pat.finditer(text):
            span = (m.start(), m.end())
            if span in seen:
                continue
            # 캡처 그룹(값)이 있는 패턴은 placeholder 값이면 건너뜀(과탐 방지).
            if code in ("generic_secret_assignment", "db_connection_string",
                        "azure_storage_key", "jdbc_password") and m.groups():
                val = m.group(1)
                if _PLACEHOLDER.match(val) or len(set(val)) <= 3:
                    continue
            seen.add(span)
            out.append(
                Violation(
                    code=code,
                    category=Category.SECRET_LEAK,
                    severity=sev,
                    reason=f"credential/secret in output: {code}",
                    start=m.start(),
                    end=m.end(),
                    matched=m.group(0)[:60],
                )
            )
    return out
