"""4관점 추천 변환 도메인 서비스.

PRD § 3.5: final_horizon_score = 0.7 * indicator_horizon_score
                                + 0.3 * issue_overall_score
변환 → RecommendationLevel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kor_trading.domain.values.recommendation import RecommendationThresholds
from kor_trading.domain.values.score import Score

if TYPE_CHECKING:
    from kor_trading.domain.services.indicator_scorer import (
        Horizon,
        IndicatorScores,
    )
    from kor_trading.domain.values.recommendation import RecommendationLevel


_DEFAULT_INDICATOR_WEIGHT = 0.7
_DEFAULT_ISSUE_WEIGHT = 0.3
_THRESHOLDS = RecommendationThresholds()


@dataclass(frozen=True, slots=True)
class HorizonRecommendation:
    horizon: Horizon
    score: Score
    level: RecommendationLevel


def derive_horizon_recommendations(
    indicator_scores: IndicatorScores,
    issue_score: float = 0.0,
    *,
    thresholds: RecommendationThresholds = _THRESHOLDS,
    indicator_weight: float = _DEFAULT_INDICATOR_WEIGHT,
    issue_weight: float = _DEFAULT_ISSUE_WEIGHT,
) -> dict[Horizon, HorizonRecommendation]:
    """관점별 종합 점수 + 추천 등급 산출.

    issue_score: -1.0~+1.0 (호재/악재 누적). 없으면 0.
    """
    if not -1.0 <= issue_score <= 1.0:
        raise ValueError(f"issue_score out of range [-1,1]: {issue_score}")

    result: dict[Horizon, HorizonRecommendation] = {}
    for horizon, ind_score in indicator_scores.by_horizon.items():
        combined = indicator_weight * ind_score.value + issue_weight * issue_score
        clamped = max(-1.0, min(1.0, combined))
        score = Score(clamped)
        result[horizon] = HorizonRecommendation(
            horizon=horizon, score=score, level=thresholds.classify(score)
        )
    return result
