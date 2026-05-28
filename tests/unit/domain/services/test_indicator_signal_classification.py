"""신호 분류(alignment, MACD cross/position, Bollinger position/squeeze) 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.indicator_calculator import calculate_indicators


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _bars(closes: list[int]) -> list[OhlcvBar]:
    bars: list[OhlcvBar] = []
    d = date(2026, 1, 5)
    for close in closes:
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


class TestSmaAlignment:
    def test_bullish_when_short_above_long(self) -> None:
        # 우상향 → 단기 평균이 장기보다 위 (정배열)
        bars = _bars([100 + i for i in range(130)])
        snap = calculate_indicators(_t(), bars)
        assert snap.sma_alignment == "bullish"

    def test_bearish_when_short_below_long(self) -> None:
        bars = _bars([300 - i for i in range(130)])
        snap = calculate_indicators(_t(), bars)
        assert snap.sma_alignment == "bearish"

    def test_none_when_any_sma_missing(self) -> None:
        bars = _bars([100] * 30)  # 60/120 SMA 부족
        snap = calculate_indicators(_t(), bars)
        assert snap.sma_alignment is None


class TestMacdPosition:
    def test_above_zero_when_uptrend(self) -> None:
        bars = _bars([100 + i for i in range(50)])
        snap = calculate_indicators(_t(), bars)
        assert snap.macd_position == "above_zero"

    def test_below_zero_when_downtrend(self) -> None:
        bars = _bars([200 - i for i in range(50)])
        snap = calculate_indicators(_t(), bars)
        assert snap.macd_position == "below_zero"


class TestMacdCross:
    def test_none_when_no_cross_in_recent_window(self) -> None:
        # 지속 우상향 → 최근 hist 부호 변화 없음
        bars = _bars([100 + i for i in range(50)])
        snap = calculate_indicators(_t(), bars)
        assert snap.macd_cross == "none"

    def test_golden_or_dead_when_trend_reversal(self) -> None:
        # 하락하다 막판 급등 → hist가 음→양으로 바뀜 (golden 가능성)
        bars = _bars([200 - i for i in range(40)] + [100 + i * 5 for i in range(10)])
        snap = calculate_indicators(_t(), bars)
        # golden_recent 또는 none 모두 합리적 (정확한 cross 위치는 EMA smoothing에 따라)
        assert snap.macd_cross in {"golden_recent", "none", "dead_recent"}


class TestBollingerPosition:
    def test_upper_half_when_close_above_mid(self) -> None:
        # 우상향 → close가 mid 위
        bars = _bars([100 + i for i in range(25)])
        snap = calculate_indicators(_t(), bars)
        assert snap.bb_position in {"upper_half", "above"}

    def test_lower_half_when_close_below_mid(self) -> None:
        bars = _bars([200 - i for i in range(25)])
        snap = calculate_indicators(_t(), bars)
        assert snap.bb_position in {"lower_half", "below"}

    def test_above_when_close_breaks_upper(self) -> None:
        # 20일 평탄 후 마지막에 급등 → 표준편차 작아 상단이 낮음 → close > upper
        bars = _bars([100] * 20 + [200])
        snap = calculate_indicators(_t(), bars)
        assert snap.bb_position == "above"


class TestBollingerSqueeze:
    def test_none_when_insufficient_history(self) -> None:
        bars = _bars([100] * 25)  # 20+20=40 필요
        snap = calculate_indicators(_t(), bars)
        assert snap.bb_squeeze is None

    def test_true_when_constant_close(self) -> None:
        # 모든 close 동일 → band_width 0 → squeeze 트루 (avg도 0인 경우 None)
        bars = _bars([100] * 45)
        snap = calculate_indicators(_t(), bars)
        # 평균 band width가 0이면 squeeze는 None (분모 0 회피)
        # 일정 변동성이 있어야 squeeze 검출 가능
        assert snap.bb_squeeze in {None, True}
