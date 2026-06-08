"""IndicatorScorer 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.indicator_scorer import compute_scores


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _snap(**overrides: object) -> IndicatorSnapshot:
    base = {"ticker": _t(), "as_of": date(2026, 5, 26)}
    base.update(overrides)
    return IndicatorSnapshot(**base)  # type: ignore[arg-type]


class TestEmptySnapshot:
    def test_all_zero_when_no_data(self) -> None:
        scores = compute_scores(_snap())
        assert scores.overall.value == 0.0
        for v in scores.category.values():
            assert v.value == 0.0


class TestTrendScore:
    def test_bullish_alignment_plus_above_zero_plus_golden(self) -> None:
        snap = _snap(
            sma_alignment="bullish", macd_position="above_zero", macd_cross="golden_recent"
        )
        scores = compute_scores(snap)
        assert scores.category["trend"].value == pytest.approx(1.0)

    def test_bearish_alignment_plus_below_zero_plus_dead(self) -> None:
        snap = _snap(sma_alignment="bearish", macd_position="below_zero", macd_cross="dead_recent")
        scores = compute_scores(snap)
        assert scores.category["trend"].value == pytest.approx(-1.0)


class TestMomentumScore:
    # RSI만 있을 때 momentum = RSI 컴포넌트 (단일)
    def test_rsi_50_to_70(self) -> None:
        assert compute_scores(_snap(rsi_14=60)).category["momentum"].value == 0.3

    def test_rsi_above_80_negative(self) -> None:
        assert compute_scores(_snap(rsi_14=85)).category["momentum"].value == -0.4

    def test_rsi_below_30(self) -> None:
        assert compute_scores(_snap(rsi_14=20)).category["momentum"].value == 0.2

    def test_rsi_70_to_80_mild_positive(self) -> None:
        assert compute_scores(_snap(rsi_14=75)).category["momentum"].value == 0.2

    def test_rsi_30_to_50_negative(self) -> None:
        assert compute_scores(_snap(rsi_14=40)).category["momentum"].value == -0.3

    def test_intraday_plunge_drags_momentum_negative(self) -> None:
        # RSI 중립(60)이어도 당일 급락이면 모멘텀 음수로
        s = _snap(rsi_14=60, change_pct_1d=-9.92)
        # (0.3 + (-0.7)) / 2 = -0.2
        assert compute_scores(s).category["momentum"].value < 0

    def test_5d_return_lifts_momentum(self) -> None:
        s = _snap(rsi_14=60, return_5d=15.0)  # 5일 +15% → +1.0
        # (0.3 + 1.0) / 2 = 0.65
        assert compute_scores(s).category["momentum"].value > 0.5

    def test_intraday_surge_penalized(self) -> None:
        # 당일 +10% 급등 → 과열 페널티 (-0.1)
        s = _snap(change_pct_1d=10.0)
        assert compute_scores(s).category["momentum"].value < 0

    def test_intraday_rise_positive(self) -> None:
        s = _snap(change_pct_1d=5.0)  # +3~8% 상승 → +0.3
        assert compute_scores(s).category["momentum"].value > 0

    def test_intraday_moderate_drop(self) -> None:
        s = _snap(change_pct_1d=-4.0)  # -3~-7% → -0.3
        assert compute_scores(s).category["momentum"].value < 0


class TestVolatilityScore:
    def test_squeeze_in_upper_half_positive(self) -> None:
        snap = _snap(bb_squeeze=True, bb_position="upper_half")
        assert compute_scores(snap).category["volatility"].value == 0.5

    def test_above_upper_negative(self) -> None:
        snap = _snap(bb_position="above")
        assert compute_scores(snap).category["volatility"].value == -0.3

    def test_below_lower_positive(self) -> None:
        snap = _snap(bb_position="below")
        assert compute_scores(snap).category["volatility"].value == 0.3


class TestVolumeScore:
    def test_obv_up_positive(self) -> None:
        assert compute_scores(_snap(obv_trend="up")).category["volume"].value == 0.4

    def test_obv_down_negative(self) -> None:
        assert compute_scores(_snap(obv_trend="down")).category["volume"].value == -0.4

    def test_volume_spike_adds(self) -> None:
        s = _snap(obv_trend="up", volume_spike=2.5)  # 0.4 + 0.3 = 0.7
        assert compute_scores(s).category["volume"].value == pytest.approx(0.7)

    def test_volume_spike_below_threshold_no_bonus(self) -> None:
        s = _snap(obv_trend="up", volume_spike=1.5)
        assert compute_scores(s).category["volume"].value == 0.4


class TestFlowScore:
    def test_both_positive_max(self) -> None:
        snap = _snap(foreign_net_buy_5d=1_000_000_000, institution_net_buy_5d=500_000_000)
        assert compute_scores(snap).category["flow"].value == pytest.approx(0.7)

    def test_both_negative(self) -> None:
        snap = _snap(foreign_net_buy_5d=-1, institution_net_buy_5d=-1)
        assert compute_scores(snap).category["flow"].value == pytest.approx(-0.7)

    def test_zero_values_contribute_nothing(self) -> None:
        snap = _snap(foreign_net_buy_5d=0, institution_net_buy_5d=0)
        assert compute_scores(snap).category["flow"].value == 0.0


class TestOverall:
    def test_strong_bull_setup(self) -> None:
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
        # 가중합: 0.25*1 + 0.20*0.5 + 0.10*0 + 0.15*0.5 + 0.30*0.7 = 0.635
        assert scores.overall.value > 0.5


class TestHorizonScores:
    def test_all_four_horizons_present(self) -> None:
        scores = compute_scores(_snap())
        assert set(scores.by_horizon.keys()) == {"ultra_short", "short", "medium", "long"}

    def test_long_emphasizes_trend_over_volume(self) -> None:
        # 거래량만 강함 → 단기에서 가산, 장기에서는 약함
        snap = _snap(obv_trend="up")
        scores = compute_scores(snap)
        assert scores.by_horizon["ultra_short"].value > scores.by_horizon["long"].value
