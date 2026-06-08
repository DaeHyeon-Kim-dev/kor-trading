"""RecommendationThresholds 분류 테스트."""

from kor_trading.domain.values.recommendation import (
    RecommendationLevel,
    RecommendationThresholds,
)
from kor_trading.domain.values.score import Score


class TestThresholdClassification:
    def test_strong_buy_at_threshold(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(0.55)) == RecommendationLevel.STRONG_BUY
        assert t.classify(Score(0.9)) == RecommendationLevel.STRONG_BUY

    def test_buy_band(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(0.4)) == RecommendationLevel.BUY
        assert t.classify(Score(0.35)) == RecommendationLevel.BUY

    def test_weak_positive_is_hold(self) -> None:
        # 약한 양의 점수(0.3)는 Buy가 아니라 Hold (스윙 엄격화)
        t = RecommendationThresholds()
        assert t.classify(Score(0.3)) == RecommendationLevel.HOLD
        assert t.classify(Score(0.0)) == RecommendationLevel.HOLD
        assert t.classify(Score(-0.3)) == RecommendationLevel.HOLD

    def test_sell_band(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(-0.4)) == RecommendationLevel.SELL

    def test_strong_sell(self) -> None:
        t = RecommendationThresholds()
        assert t.classify(Score(-0.55)) == RecommendationLevel.STRONG_SELL
        assert t.classify(Score(-1.0)) == RecommendationLevel.STRONG_SELL

    def test_custom_thresholds(self) -> None:
        t = RecommendationThresholds(strong_buy=0.7, buy=0.3, sell=-0.3, strong_sell=-0.7)
        assert t.classify(Score(0.5)) == RecommendationLevel.BUY
