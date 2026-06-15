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
]

# 명백한 placeholder/예시는 generic 오탐에서 제외.
_PLACEHOLDER = re.compile(
    r"(?i)^(?:your|my|the|example|placeholder|xxx+|<.*>|\.\.\.|insert|todo|changeme|"
    r"abc123|0+|1+|test|dummy|sample|redacted|\*+)",
)


def scan_secrets(text: str) -> list[Violation]:
    out: list[Violation] = []
    seen: set[tuple[int, int]] = set()
    for code, pat, sev in _PATTERNS:
        for m in pat.finditer(text):
            span = (m.start(), m.end())
            if span in seen:
                continue
            # generic 할당은 placeholder 값이면 건너뜀(과탐 방지).
            if code == "generic_secret_assignment":
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
