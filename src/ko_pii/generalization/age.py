"""연령 일반화 — 1세 단위 → 10세 (또는 임의 폭) 구간."""
from __future__ import annotations


def generalize_age(age: int, bucket_size: int = 10) -> str:
    """Return e.g. ``"30대"`` for age=34, bucket_size=10.

    For ages below ``bucket_size`` returns ``"미성년"`` style label is OUT OF
    scope here — we keep this purely numeric. 95+ is bucketed into ``"90대"``.
    """
    if age < 0:
        raise ValueError("age must be non-negative")
    if bucket_size <= 0:
        raise ValueError("bucket_size must be positive")
    bucket_start = (age // bucket_size) * bucket_size
    return f"{bucket_start}대"
