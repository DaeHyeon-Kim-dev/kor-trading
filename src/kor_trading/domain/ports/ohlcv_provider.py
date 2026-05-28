"""종목별 일봉 시계열 fetch 포트."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.ohlcv_bar import OhlcvBar


@runtime_checkable
class OhlcvProvider(Protocol):
    """특정 종목의 과거 일봉 시계열을 제공.

    어댑터(예: pykrx)가 구현. 도메인은 추상에만 의존.
    """

    def get_daily_bars(self, ticker_code: str, end_date: date, days: int) -> list[OhlcvBar]:
        """end_date 종료, days만큼 거슬러 올라간 일봉. 휴장일 자동 제외."""
        ...
