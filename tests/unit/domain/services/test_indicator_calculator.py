"""지표 계산 도메인 서비스 테스트."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.indicator_calculator import calculate_indicators


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _bars(closes: list[int], start: date = date(2026, 1, 5)) -> list[OhlcvBar]:
    """단순 일봉 시계열 — open=high=low=close, volume=1000."""
    bars: list[OhlcvBar] = []
    d = start
    for close in closes:
        # 비즈니스데이 가정 — 주말 건너뜀
        while d.isoweekday() > 5:
            d += timedelta(days=1)
        bars.append(
            OhlcvBar(
                date=d,
                open=close,
                high=close + 100,
                low=max(0, close - 100),
                close=close,
                volume=1000,
                trading_value=close * 1000,
            )
        )
        d += timedelta(days=1)
    return bars


class TestEmptyInput:
    def test_returns_all_none_when_no_bars(self) -> None:
        snap = calculate_indicators(_t(), [])
        assert snap.sma_5 is None
        assert snap.macd is None
        assert snap.rsi_14 is None
        assert snap.bb_upper is None


class TestSma:
    def test_sma_5_constant_close(self) -> None:
        bars = _bars([100] * 10)
        snap = calculate_indicators(_t(), bars)
        assert snap.sma_5 == 100.0
        assert snap.sma_20 is None  # 데이터 부족

    def test_sma_20_when_enough(self) -> None:
        bars = _bars([100] * 25)
        snap = calculate_indicators(_t(), bars)
        assert snap.sma_5 == 100.0
        assert snap.sma_20 == 100.0
        assert snap.sma_60 is None
        assert snap.sma_120 is None

    def test_sma_120_when_long_history(self) -> None:
        bars = _bars([100] * 130)
        snap = calculate_indicators(_t(), bars)
        assert snap.sma_120 == 100.0


class TestMacd:
    def test_none_when_insufficient_history(self) -> None:
        bars = _bars([100] * 30)  # 26+9=35 필요
        snap = calculate_indicators(_t(), bars)
        assert snap.macd is None

    def test_zero_when_constant_close(self) -> None:
        bars = _bars([100] * 50)
        snap = calculate_indicators(_t(), bars)
        assert snap.macd is not None
        assert abs(snap.macd) < 1e-6
        assert snap.macd_hist is not None
        assert abs(snap.macd_hist) < 1e-6

    def test_positive_when_uptrend(self) -> None:
        bars = _bars([100 + i for i in range(50)])
        snap = calculate_indicators(_t(), bars)
        assert snap.macd is not None
        assert snap.macd > 0


class TestRsi:
    def test_none_when_insufficient(self) -> None:
        bars = _bars([100] * 10)  # 15개 필요 (14+1)
        snap = calculate_indicators(_t(), bars)
        assert snap.rsi_14 is None

    def test_rsi_at_100_when_pure_uptrend(self) -> None:
        bars = _bars([100 + i for i in range(30)])
        snap = calculate_indicators(_t(), bars)
        assert snap.rsi_14 is not None
        assert snap.rsi_14 == pytest.approx(100.0, abs=0.5)

    def test_rsi_at_zero_when_pure_downtrend(self) -> None:
        bars = _bars([100 - i for i in range(30)])
        snap = calculate_indicators(_t(), bars)
        assert snap.rsi_14 is not None
        assert snap.rsi_14 == pytest.approx(0.0, abs=0.5)


class TestBollinger:
    def test_none_when_insufficient(self) -> None:
        bars = _bars([100] * 10)
        snap = calculate_indicators(_t(), bars)
        assert snap.bb_upper is None

    def test_constant_close_bands_equal(self) -> None:
        bars = _bars([100] * 25)
        snap = calculate_indicators(_t(), bars)
        assert snap.bb_mid == pytest.approx(100.0)
        # 표준편차 0이면 상하단도 100
        assert snap.bb_upper == pytest.approx(100.0)
        assert snap.bb_lower == pytest.approx(100.0)


class TestAtr:
    def test_none_when_insufficient(self) -> None:
        bars = _bars([100] * 10)
        snap = calculate_indicators(_t(), bars)
        assert snap.atr_14 is None

    def test_constant_close_atr_is_high_low_range(self) -> None:
        # _bars helper: high=close+100, low=close-100 → TR=200
        bars = _bars([100] * 20)
        snap = calculate_indicators(_t(), bars)
        assert snap.atr_14 == pytest.approx(200.0, abs=5)


class TestStochastic:
    def test_none_when_insufficient(self) -> None:
        bars = _bars([100] * 10)
        snap = calculate_indicators(_t(), bars)
        assert snap.stoch_k is None
        assert snap.stoch_d is None

    def test_stoch_above_50_when_uptrend(self) -> None:
        # 우상향 — close가 14일 최고가 근방 (high-low band 때문에 100% 못 닿음)
        bars = _bars([100 + i * 10 for i in range(20)])
        snap = calculate_indicators(_t(), bars)
        assert snap.stoch_k is not None
        assert snap.stoch_k > 50

    def test_stoch_none_when_flat_ohlc(self) -> None:
        # OHLC가 모두 동일 → range=0 → stochastic 정의 불가 → None
        bars: list[OhlcvBar] = []
        d = date(2026, 1, 5)
        for _ in range(20):
            while d.isoweekday() > 5:
                d += timedelta(days=1)
            bars.append(
                OhlcvBar(
                    date=d,
                    open=100,
                    high=100,
                    low=100,
                    close=100,
                    volume=1,
                    trading_value=100,
                )
            )
            d += timedelta(days=1)
        snap = calculate_indicators(_t(), bars)
        assert snap.stoch_k is None
        assert snap.stoch_d is None


class TestObvTrend:
    def test_none_when_insufficient(self) -> None:
        bars = _bars([100] * 10)  # 20 미만
        snap = calculate_indicators(_t(), bars)
        assert snap.obv_trend is None

    def test_up_when_rising_prices(self) -> None:
        # 지속 상승 → 매일 거래량이 OBV에 +로 누적
        bars = _bars([100 + i for i in range(30)])
        snap = calculate_indicators(_t(), bars)
        assert snap.obv_trend == "up"

    def test_down_when_falling_prices(self) -> None:
        bars = _bars([200 - i for i in range(30)])
        snap = calculate_indicators(_t(), bars)
        assert snap.obv_trend == "down"

    def test_flat_when_constant_prices(self) -> None:
        # 종가 동일 → direction 0 → OBV 변화 없음
        bars = _bars([100] * 30)
        snap = calculate_indicators(_t(), bars)
        assert snap.obv_trend == "flat"


class TestAsOf:
    def test_uses_last_bar_date(self) -> None:
        bars = _bars([100] * 5)
        snap = calculate_indicators(_t(), bars)
        assert snap.as_of == bars[-1].date
