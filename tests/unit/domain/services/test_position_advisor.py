"""보유 포지션 관리 테스트."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.position_advisor import manage_position

_T = Ticker(code="005930", name="X", market="KOSPI")


def _snap(**kw: Any) -> IndicatorSnapshot:
    return IndicatorSnapshot(ticker=_T, as_of=date(2026, 6, 11), **kw)


class TestGuards:
    def test_non_positive_avg_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="avg_cost"):
            manage_position(_snap(sma_20=9000.0), close=9500, avg_cost=0)


class TestPnl:
    def test_pnl_pct(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bullish", sma_20=9000.0), close=11_000, avg_cost=10_000
        )
        assert adv.pnl_pct == 10.0


class TestTrendBroken:
    def test_bearish_in_profit_take_all(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bearish", sma_20=9000.0), close=9500, avg_cost=9000
        )
        assert adv.action == "전량 익절"

    def test_below_ma_in_loss_cut(self) -> None:
        # close < 20일선*0.97 → 추세 이탈 + 손실 → 손절
        adv = manage_position(_snap(sma_20=10_000.0, atr_14=200.0), close=9000, avg_cost=9500)
        assert adv.action == "손절"
        assert "손절" in adv.reason


class TestOverextended:
    def test_high_rsi_in_profit_trim(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bullish", sma_20=9000.0, rsi_14=80.0), close=9500, avg_cost=9000
        )
        assert adv.action == "일부 익절"

    def test_band_above_in_profit_trim(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bullish", sma_20=9000.0, bb_position="above"),
            close=9500,
            avg_cost=9000,
        )
        assert adv.action == "일부 익절"

    def test_overextended_but_loss_holds(self) -> None:
        # 과열이지만 손실 구간 → 일부익절 아님 → 보유
        adv = manage_position(
            _snap(sma_alignment="bullish", sma_20=9000.0, rsi_14=80.0), close=9500, avg_cost=10_000
        )
        assert adv.action == "보유"


class TestPullbackAdd:
    def test_pullback_suggests_add(self) -> None:
        snap = _snap(
            sma_alignment="bullish",
            sma_5=9_550.0,
            sma_20=9_400.0,
            rsi_14=50.0,
            change_pct_1d=-1.0,
            atr_14=200.0,
        )
        adv = manage_position(snap, close=9_500, avg_cost=9_000)
        assert adv.action == "추가매수 검토"


class TestHold:
    def test_default_hold(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bullish", sma_20=9000.0, rsi_14=60.0, bb_position="upper_half"),
            close=9500,
            avg_cost=9000,
        )
        assert adv.action == "보유"


class TestStopAndNote:
    def test_stop_from_ma(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bullish", sma_20=10_000.0), close=10_500, avg_cost=9000
        )
        assert adv.stop_level == 9_700  # 10000 * 0.97
        assert "권장 손절선" in adv.note
        assert "20일선" in adv.note

    def test_stop_from_atr_when_no_ma(self) -> None:
        adv = manage_position(
            _snap(sma_alignment="bullish", atr_14=200.0), close=10_000, avg_cost=9000
        )
        assert adv.stop_level == 9_600  # 10000 - 2*200

    def test_stop_zero_when_no_levels(self) -> None:
        adv = manage_position(_snap(sma_alignment="bullish"), close=10_000, avg_cost=9000)
        assert adv.stop_level == 0
        assert "산출 불가" in adv.note

    def test_stop_zero_keeps_ma_note(self) -> None:
        # 가격이 20일선 아래 + ATR 없음 → 손절선 0이지만 20일선은 안내
        adv = manage_position(_snap(sma_20=10_000.0), close=9000, avg_cost=9500)
        assert adv.stop_level == 0
        assert "20일선" in adv.note
        assert "권장 손절선" not in adv.note

    def test_atr_stop_skipped_when_nonpositive(self) -> None:
        # close보다 큰 ATR → 손절가 음수 → 0
        adv = manage_position(_snap(sma_alignment="bullish", atr_14=80.0), close=100, avg_cost=90)
        assert adv.stop_level == 0
