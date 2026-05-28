"""DisclosureProvider Protocol 부합 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.ports.disclosure_provider import DisclosureProvider

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.disclosure import Disclosure


class _StubProvider:
    def get_recent(self, ticker_code: str, end_date: date, lookback_days: int) -> list[Disclosure]:
        _ = (ticker_code, end_date, lookback_days)
        return []


class TestDisclosureProviderProtocol:
    def test_stub_conforms_to_protocol(self) -> None:
        assert isinstance(_StubProvider(), DisclosureProvider)
