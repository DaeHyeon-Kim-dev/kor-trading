"""indicator_explainer 테스트."""

from __future__ import annotations

from datetime import date

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.indicator_explainer import (
    explain_indicators,
    summarize_signal,
)


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _snap(**over: object) -> IndicatorSnapshot:
    base: dict[str, object] = {"ticker": _t(), "as_of": date(2026, 5, 26)}
    base.update(over)
    return IndicatorSnapshot(**base)  # type: ignore[arg-type]


class TestExplain:
    def test_empty_when_no_data(self) -> None:
        assert explain_indicators(_snap()) == []

    def test_alignment_explained_in_korean(self) -> None:
        lines = explain_indicators(_snap(sma_alignment="bullish"))
        assert any("정배열" in line and "상승추세" in line for line in lines)

    def test_rsi_label_neutral_strong(self) -> None:
        lines = explain_indicators(_snap(rsi_14=55.0))
        assert any("RSI 55.0" in line and "중립~강세" in line for line in lines)

    def test_rsi_overbought(self) -> None:
        lines = explain_indicators(_snap(rsi_14=85.0))
        assert any("과매수" in line for line in lines)

    def test_rsi_oversold(self) -> None:
        lines = explain_indicators(_snap(rsi_14=20.0))
        assert any("과매도" in line for line in lines)

    def test_macd_combines_position_and_cross(self) -> None:
        lines = explain_indicators(_snap(macd_position="above_zero", macd_cross="golden_recent"))
        macd_line = next(line for line in lines if line.startswith("MACD"))
        assert "강세권" in macd_line
        assert "골든크로스" in macd_line

    def test_bollinger_squeeze_appended(self) -> None:
        lines = explain_indicators(_snap(bb_position="upper_half", bb_squeeze=True))
        bb_line = next(line for line in lines if "볼린저" in line)
        assert "수축" in bb_line

    def test_foreign_flow_buy(self) -> None:
        lines = explain_indicators(_snap(foreign_net_buy_5d=12_500_000_000))
        assert any("외국인" in line and "매수 우위" in line for line in lines)

    def test_institution_flow_sell(self) -> None:
        lines = explain_indicators(_snap(institution_net_buy_5d=-3_200_000_000))
        assert any("기관" in line and "매도 우위" in line for line in lines)

    def test_obv_trend(self) -> None:
        lines = explain_indicators(_snap(obv_trend="up"))
        assert any("OBV" in line and "매집" in line for line in lines)

    def test_rsi_neutral_weak_range(self) -> None:
        lines = explain_indicators(_snap(rsi_14=40.0))
        assert any("중립~약세" in line for line in lines)

    def test_flow_zero_is_neutral(self) -> None:
        lines = explain_indicators(_snap(foreign_net_buy_5d=0))
        assert any("외국인" in line and "중립" in line for line in lines)


class TestSummarize:
    def test_data_missing(self) -> None:
        assert summarize_signal(_snap()) == "데이터 부족"

    def test_bullish_summary(self) -> None:
        s = summarize_signal(
            _snap(
                sma_alignment="bullish",
                macd_cross="golden_recent",
                rsi_14=60.0,
                obv_trend="up",
            )
        )
        assert "추세 강세" in s
        assert "골든크로스" in s
        assert "RSI 60" in s
        assert "거래량 매집" in s

    def test_bearish_summary(self) -> None:
        s = summarize_signal(_snap(sma_alignment="bearish", obv_trend="down"))
        assert "추세 약세" in s
        assert "거래량 분산" in s

    def test_dead_cross_in_summary(self) -> None:
        s = summarize_signal(_snap(macd_cross="dead_recent", rsi_14=45.0))
        assert "데드크로스" in s
        assert "RSI 45" in s
