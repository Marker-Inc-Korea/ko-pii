"""한국어 조사 처리.

이름이 보통 한국어에서 조사와 붙어 등장: "홍길동이", "홍길동은", "홍길동에게".
검출 시 조사를 분리해야 이름 표면형이 정확해진다.
"""
from __future__ import annotations

# 길이가 긴 조사부터 시도해야 옳게 매칭됨 (예: "에게" 가 "에" 보다 먼저)
PARTICLES: tuple[str, ...] = (
    "에게서", "한테서", "께서",
    "에게", "한테", "에서", "으로", "보다",
    "이가", "이는", "이도", "이를",
    "은", "는", "이", "가", "을", "를", "와", "과", "의",
    "에", "도", "만", "야", "라", "여",
)


def strip_trailing_particle(token: str) -> tuple[str, str | None]:
    """Return ``(stem, particle)`` — particle is None if none stripped."""
    for p in PARTICLES:
        if token.endswith(p) and len(token) > len(p):
            return token[: -len(p)], p
    return token, None


def starts_with_particle(token: str) -> bool:
    return any(token.startswith(p) for p in PARTICLES)
