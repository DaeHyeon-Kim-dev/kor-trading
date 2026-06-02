"""Issue 리스트 → 종목 종합 이슈 점수 (-1.0 ~ +1.0).

sentiment 방향 * effective_impact * confidence를 합산 후 clip.
여러 호재가 누적되면 점수가 강해진다 (단순 평균이 아닌 합산).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.entities.issue import Sentiment

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kor_trading.domain.entities.issue import Issue


_SENTIMENT_SIGN: dict[Sentiment, float] = {
    Sentiment.POSITIVE: 1.0,
    Sentiment.NEGATIVE: -1.0,
    Sentiment.NEUTRAL: 0.0,
}


def aggregate_issue_score(issues: Sequence[Issue]) -> float:
    """이슈들의 방향·영향·신뢰·시점을 가중 합산해 [-1, 1]로 clip."""
    if not issues:
        return 0.0
    total = 0.0
    for issue in issues:
        sign = _SENTIMENT_SIGN[issue.sentiment]
        total += sign * issue.effective_impact * issue.confidence
    return max(-1.0, min(1.0, total))
