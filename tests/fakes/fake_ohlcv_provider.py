"""In-memory FakeOhlcvProvider — 단위 테스트용."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.ohlcv_bar import OhlcvBar


class FakeOhlcvProvider:
    def __init__(self) -> None:
        self._bars: dict[str, list[OhlcvBar]] = {}
        self._raise_for: set[str] = set()

    def add_bars(self, ticker_code: str, bars: list[OhlcvBar]) -> None:
        self._bars[ticker_code] = bars

    def raise_for_ticker(self, ticker_code: str) -> None:
        self._raise_for.add(ticker_code)

    def get_daily_bars(self, ticker_code: str, end_date: date, days: int) -> list[OhlcvBar]:
        if ticker_code in self._raise_for:
            raise RuntimeError(f"fake provider configured to fail for {ticker_code}")
        bars = [b for b in self._bars.get(ticker_code, []) if b.date <= end_date]
        return bars[-days:]
