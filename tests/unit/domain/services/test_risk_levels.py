"""ATR 손절가 계산 테스트 (PRD R3)."""

from __future__ import annotations

from kor_trading.domain.services.risk_levels import (
    STANDARD_MULTIPLIER,
    TIGHT_MULTIPLIER,
    atr_stop_loss,
)


class TestAtrStopLoss:
    def test_standard_2x(self) -> None:
        sl = atr_stop_loss(close=50_000, atr=1_000.0, multiplier=STANDARD_MULTIPLIER)
        assert sl.price == 48_000  # 50000 - 2*1000
        assert sl.pct == -4.0
        assert sl.multiplier == 2.0

    def test_tight_1_5x(self) -> None:
        sl = atr_stop_loss(close=50_000, atr=1_000.0, multiplier=TIGHT_MULTIPLIER)
        assert sl.price == 48_500
        assert sl.pct == -3.0

    def test_rounds_to_won(self) -> None:
        sl = atr_stop_loss(close=10_000, atr=333.3, multiplier=2.0)
        assert sl.price == round(10_000 - 666.6)  # 9333

    def test_zero_atr_equals_close(self) -> None:
        sl = atr_stop_loss(close=10_000, atr=0.0, multiplier=2.0)
        assert sl.price == 10_000
        assert sl.pct == 0.0
