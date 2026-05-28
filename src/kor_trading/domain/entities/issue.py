"""Issue 엔티티 — 공시·뉴스를 분석한 결과.

PRD: docs/PRD.md § 3.4 — sentiment / impact / decay / effective_impact /
price_action_since / confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.disclosure import DisclosureSource


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Impact(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_IMPACT_SCORES: dict[Impact, float] = {
    Impact.HIGH: 1.0,
    Impact.MEDIUM: 0.6,
    Impact.LOW: 0.3,
}


def impact_score(impact: Impact) -> float:
    return _IMPACT_SCORES[impact]


@dataclass(frozen=True, slots=True)
class Issue:
    ticker_code: str
    date: date
    title: str
    source: DisclosureSource
    source_url: str
    sentiment: Sentiment
    impact: Impact
    confidence: float
    summary: str
    recency_days: int
    decay_weight: float
    effective_impact: float
    price_action_since: float | None = None
    report_type: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range [0,1]: {self.confidence}")
        if not 0.0 <= self.decay_weight <= 1.0:
            raise ValueError(f"decay_weight out of range [0,1]: {self.decay_weight}")
        if not 0.0 <= self.effective_impact <= 1.0:
            raise ValueError(f"effective_impact out of range [0,1]: {self.effective_impact}")
        if self.recency_days < 0:
            raise ValueError(f"recency_days non-negative: {self.recency_days}")
        if not self.title.strip():
            raise ValueError("issue title must not be blank")
