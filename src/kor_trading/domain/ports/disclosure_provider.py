"""공시·뉴스 fetch 포트."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.disclosure import Disclosure


@runtime_checkable
class DisclosureProvider(Protocol):
    """특정 종목의 최근 공시·뉴스 fetch.

    어댑터(DART/네이버 등)가 구현. 도메인은 추상에만 의존.
    """

    def get_recent(
        self, ticker_code: str, end_date: date, lookback_days: int
    ) -> list[Disclosure]: ...
