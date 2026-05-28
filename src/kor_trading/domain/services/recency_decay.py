"""시점 가중치 스케줄.

PRD: docs/PRD.md § 3.4 — recency_days별 decay_weight 표.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True, slots=True)
class RecencyDecaySchedule:
    """공시·뉴스의 시점 기반 가중치.

    PRD § 3.4 기본값:
    - 0일(당일) → 1.00 (미반영)
    - 1~2일 → 0.85
    - 3~7일 → 0.60
    - 8~14일 → 0.30
    - 15일+ → 0.10
    """

    today: float = 1.00
    days_1_to_2: float = 0.85
    days_3_to_7: float = 0.60
    days_8_to_14: float = 0.30
    days_15_plus: float = 0.10

    def weight_for(self, recency_days: int) -> float:
        if recency_days < 0:
            raise ValueError(f"recency_days must be non-negative: {recency_days}")
        if recency_days == 0:
            return self.today
        if recency_days <= 2:  # noqa: PLR2004
            return self.days_1_to_2
        if recency_days <= 7:  # noqa: PLR2004
            return self.days_3_to_7
        if recency_days <= 14:  # noqa: PLR2004
            return self.days_8_to_14
        return self.days_15_plus


def days_between(disclosure_date: date, as_of: date) -> int:
    """분석 기준일로부터 공시일까지의 일수 (음수면 ValueError)."""
    delta = (as_of - disclosure_date).days
    if delta < 0:
        raise ValueError(f"disclosure_date {disclosure_date} is after as_of {as_of}")
    return delta
