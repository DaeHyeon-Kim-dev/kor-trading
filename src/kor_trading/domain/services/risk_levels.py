"""ATR 기반 손절가 계산 — 변동성에 비례한 스윙 손절 레벨.

PRD R3 — 종목 카드/근거에 손절가를 제시.
손절가 = 현재가 - (배수 * ATR). 배수가 클수록 느슨한(여유 있는) 손절.
"""

from __future__ import annotations

from dataclasses import dataclass

# 스윙 표준: 타이트(1.5x) / 표준(2.0x)
TIGHT_MULTIPLIER = 1.5
STANDARD_MULTIPLIER = 2.0


@dataclass(frozen=True, slots=True)
class StopLoss:
    """ATR 손절 레벨 한 개."""

    multiplier: float
    price: int  # 손절가 (원)
    pct: float  # 현재가 대비 (%) — 음수


def atr_stop_loss(close: int, atr: float, multiplier: float) -> StopLoss:
    """현재가·ATR로 손절가와 현재가 대비 하락폭(%)을 계산."""
    price = round(close - multiplier * atr)
    pct = (price - close) / close * 100
    return StopLoss(multiplier=multiplier, price=price, pct=pct)
