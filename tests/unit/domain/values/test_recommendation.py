"""RecommendationThresholds 분류 테스트."""

from kor_trading.domain.values.recommendation import (
    RecommendationLevel,
    RecommendationThresholds,
)
from kor_trading.domain.values.score import Score


class TestThresholdClassification:
    def test_strong_buy_at_0_5(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(0.5)) == RecommendationLevel.STRONG_BUY
        assert t.classify(Score(0.9)) == RecommendationLevel.STRONG_BUY

    def test_buy_between_0_2_and_0_5(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(0.3)) == RecommendationLevel.BUY
        assert t.classify(Score(0.2)) == RecommendationLevel.BUY

    def test_hold_in_neutral_band(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(0.0)) == RecommendationLevel.HOLD
        assert t.classify(Score(0.1)) == RecommendationLevel.HOLD
        assert t.classify(Score(-0.1)) == RecommendationLevel.HOLD

    def test_sell_between_minus_0_5_and_minus_0_2(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(-0.3)) == RecommendationLevel.SELL

    def test_strong_sell_at_or_below_minus_0_5(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(-0.5)) == RecommendationLevel.STRONG_SELL
        assert t.classify(Score(-1.0)) == RecommendationLevel.STRONG_SELL

    def test_custom_thresholds(self) -> None:
        t = RecommendationThresholds(strong_buy=0.7, buy=0.3, sell=-0.3, strong_sell=-0.7)
        assert t.classify(Score(0.5)) == RecommendationLevel.BUY
