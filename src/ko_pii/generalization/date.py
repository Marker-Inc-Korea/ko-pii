"""날짜 일반화 — 정밀도 단계: year / month / decade."""
from __future__ import annotations

from datetime import date


def generalize_date(d: date, precision: str = "year") -> str:
    """Generalize a date.

    ``precision``:
      - ``"year"`` → ``"1988년"``
      - ``"month"`` → ``"1988-01"``
      - ``"decade"`` → ``"1980년대"``
    """
    if precision == "year":
        return f"{d.year}년"
    if precision == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if precision == "decade":
        return f"{(d.year // 10) * 10}년대"
    raise ValueError(f"Unknown precision: {precision}")
