"""OhlcvProvider Protocol 부합 테스트."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider

if TYPE_CHECKING:
    from kor_trading.domain.entities.ohlcv_bar import OhlcvBar


class _StubProvider:
    def get_daily_bars(self, ticker_code: str, end_date: date, days: int) -> list[OhlcvBar]:
        _ = (ticker_code, end_date, days)
        return []


class TestOhlcvProviderProtocol:
    def test_stub_conforms_to_protocol(self) -> None:
        provider = _StubProvider()
        assert isinstance(provider, OhlcvProvider)

    def test_returns_empty_list_when_no_data(self) -> None:
        provider = _StubProvider()
        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 120)
        assert bars == []
