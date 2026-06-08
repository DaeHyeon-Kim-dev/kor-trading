"""derive_horizon_recommendations 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.horizon_recommendation import (
    derive_horizon_recommendations,
)
from kor_trading.domain.services.indicator_scorer import compute_scores
from kor_trading.domain.values.recommendation import RecommendationLevel


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _snap(**overrides: object) -> IndicatorSnapshot:
    base = {"ticker": _t(), "as_of": date(2026, 5, 26)}
    base.update(overrides)
    return IndicatorSnapshot(**base)  # type: ignore[arg-type]


class TestBasic:
    def test_all_horizons_included(self) -> None:
        scores = compute_scores(_snap())
        result = derive_horizon_recommendations(scores)
        assert set(result.keys()) == {"ultra_short", "short", "medium", "long"}

    def test_neutral_indicator_neutral_issue_yields_hold(self) -> None:
        scores = compute_scores(_snap())
        result = derive_horizon_recommendations(scores, issue_score=0.0)
        for rec in result.values():
            assert rec.level == RecommendationLevel.HOLD


class TestRationale:
    def test_neutral_has_no_signal_rationale(self) -> None:
        scores = compute_scores(_snap())
        result = derive_horizon_recommendations(scores)
        assert result["short"].rationale == "뚜렷한 신호 없음(중립)"

    def test_bullish_rationale_lists_contributors(self) -> None:
        snap = _snap(
            sma_alignment="bullish",
            macd_position="above_zero",
            macd_cross="golden_recent",
            rsi_14=60,
            obv_trend="up",
            foreign_net_buy_5d=1_000_000_000,
            institution_net_buy_5d=500_000_000,
        )
        result = derive_horizon_recommendations(compute_scores(snap), issue_score=0.8)
        rationale = result["short"].rationale
        assert "추세 강세" in rationale
        assert "수급 유입" in rationale
        assert "호재 우세" in rationale

    def test_negative_issue_in_rationale(self) -> None:
        scores = compute_scores(_snap(sma_alignment="bearish"))
        result = derive_horizon_recommendations(scores, issue_score=-0.9)
        assert "악재 우세" in result["short"].rationale
        assert "추세 약세" in result["short"].rationale


class TestWithIssueBoost:
    def test_strong_indicator_plus_positive_issue_yields_strong_buy(self) -> None:
        snap = _snap(
            sma_alignment="bullish",
            macd_position="above_zero",
            macd_cross="golden_recent",
            rsi_14=60,
            obv_trend="up",
            foreign_net_buy_5d=1_000_000_000,
            institution_net_buy_5d=500_000_000,
        )
        scores = compute_scores(snap)
        result = derive_horizon_recommendations(scores, issue_score=0.8)
        # 적어도 short/medium 관점은 strong_buy일 정도로 강력
        assert result["short"].level == RecommendationLevel.STRONG_BUY

    def test_negative_issue_drags_down(self) -> None:
        snap = _snap(
            sma_alignment="bullish",
            macd_position="above_zero",
            rsi_14=60,
        )
        positive_only = derive_horizon_recommendations(compute_scores(snap), issue_score=0.0)
        with_bad_news = derive_horizon_recommendations(compute_scores(snap), issue_score=-0.9)
        for h in positive_only:
            assert with_bad_news[h].score.value < positive_only[h].score.value


class TestValidation:
    def test_invalid_issue_score_raises(self) -> None:
        scores = compute_scores(_snap())
        with pytest.raises(ValueError, match="issue_score"):
            derive_horizon_recommendations(scores, issue_score=1.5)


class TestClampingScore:
    def test_extreme_inputs_stay_in_bound(self) -> None:
        snap = _snap(
            sma_alignment="bullish",
            macd_position="above_zero",
            macd_cross="golden_recent",
            rsi_14=60,
            obv_trend="up",
            foreign_net_buy_5d=1,
            institution_net_buy_5d=1,
        )
        scores = compute_scores(snap)
        result = derive_horizon_recommendations(
            scores, issue_score=1.0, indicator_weight=2.0, issue_weight=2.0
        )
        for rec in result.values():
            assert -1.0 <= rec.score.value <= 1.0
