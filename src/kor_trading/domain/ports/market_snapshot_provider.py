from datetime import date
from typing import Protocol, runtime_checkable

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market


@runtime_checkable
class MarketSnapshotProvider(Protocol):
    """특정 시점의 시장 전체 종목 스냅샷을 제공하는 포트.

    어댑터(예: pykrx)가 구현. 도메인은 추상에만 의존.
    """

    def get_market_snapshots(
        self, markets: tuple[Market, ...], as_of: date
    ) -> list[StockSnapshot]: ...
