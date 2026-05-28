"""추천 등급 값 객체.

PRD: docs/PRD.md § 3.5 — Strong Buy / Buy / Hold / Sell / Strong Sell.
config/default.yaml § reporting.recommendation_levels 임계값.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kor_trading.domain.values.score import Score


class RecommendationLevel(StrEnum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass(frozen=True, slots=True)
class RecommendationThresholds:
    strong_buy: float = 0.5
    buy: float = 0.2
    sell: float = -0.2
    strong_sell: float = -0.5

    def classify(self, score: Score) -> RecommendationLevel:
        v = score.value
        if v >= self.strong_buy:
            return RecommendationLevel.STRONG_BUY
        if v >= self.buy:
            return RecommendationLevel.BUY
        if v > self.sell:
            return RecommendationLevel.HOLD
        if v > self.strong_sell:
            return RecommendationLevel.SELL
        return RecommendationLevel.STRONG_SELL
