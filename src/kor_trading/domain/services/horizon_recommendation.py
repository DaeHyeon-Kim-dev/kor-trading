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
        Category,
        Horizon,
        IndicatorScores,
    )
    from kor_trading.domain.values.recommendation import RecommendationLevel


_DEFAULT_INDICATOR_WEIGHT = 0.7
_DEFAULT_ISSUE_WEIGHT = 0.3
_THRESHOLDS = RecommendationThresholds()

# 카테고리 점수 → 자연어 근거 임계값
_STRONG = 0.3
_ISSUE_STRONG = 0.2

_CATEGORY_KO: dict[str, tuple[str, str]] = {
    # (양의 기여 표현, 음의 기여 표현)
    "trend": ("추세 강세", "추세 약세"),
    "momentum": ("모멘텀 양호", "모멘텀 둔화"),
    "volatility": ("변동성 우호", "변동성 부담"),
    "volume": ("거래량 매집", "거래량 분산"),
    "flow": ("수급 유입", "수급 이탈"),
}


@dataclass(frozen=True, slots=True)
class HorizonRecommendation:
    horizon: Horizon
    score: Score
    level: RecommendationLevel
    rationale: str = ""


def derive_horizon_recommendations(
    indicator_scores: IndicatorScores,
    issue_score: float = 0.0,
    *,
    thresholds: RecommendationThresholds = _THRESHOLDS,
    indicator_weight: float = _DEFAULT_INDICATOR_WEIGHT,
    issue_weight: float = _DEFAULT_ISSUE_WEIGHT,
) -> dict[Horizon, HorizonRecommendation]:
    """관점별 종합 점수 + 추천 등급 + 근거 산출.

    issue_score: -1.0~+1.0 (호재/악재 누적). 없으면 0.
    """
    if not -1.0 <= issue_score <= 1.0:
        raise ValueError(f"issue_score out of range [-1,1]: {issue_score}")

    rationale = _build_rationale(indicator_scores.category, issue_score)

    result: dict[Horizon, HorizonRecommendation] = {}
    for horizon, ind_score in indicator_scores.by_horizon.items():
        combined = indicator_weight * ind_score.value + issue_weight * issue_score
        clamped = max(-1.0, min(1.0, combined))
        score = Score(clamped)
        result[horizon] = HorizonRecommendation(
            horizon=horizon,
            score=score,
            level=thresholds.classify(score),
            rationale=rationale,
        )
    return result


def _build_rationale(category: dict[Category, Score], issue_score: float) -> str:
    """카테고리 기여 + 이슈 방향을 자연어 근거로."""
    parts: list[str] = []
    for cat, score in category.items():
        pos, neg = _CATEGORY_KO[cat]
        if score.value >= _STRONG:
            parts.append(pos)
        elif score.value <= -_STRONG:
            parts.append(neg)
    if issue_score >= _ISSUE_STRONG:
        parts.append("호재 우세")
    elif issue_score <= -_ISSUE_STRONG:
        parts.append("악재 우세")

    if not parts:
        return "뚜렷한 신호 없음(중립)"
    return " + ".join(parts)
