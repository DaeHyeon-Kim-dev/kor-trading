"""in-memory FakeDisclosureProvider."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.disclosure import Disclosure


class FakeDisclosureProvider:
    def __init__(self) -> None:
        self._by_ticker: dict[str, list[Disclosure]] = {}
        self._raise_for: set[str] = set()

    def add(self, ticker_code: str, disclosures: list[Disclosure]) -> None:
        self._by_ticker[ticker_code] = disclosures

    def raise_for_ticker(self, ticker_code: str) -> None:
        self._raise_for.add(ticker_code)

    def get_recent(self, ticker_code: str, end_date: date, lookback_days: int) -> list[Disclosure]:
        _ = (end_date, lookback_days)
        if ticker_code in self._raise_for:
            raise RuntimeError(f"fake disclosure failure for {ticker_code}")
        return self._by_ticker.get(ticker_code, [])
