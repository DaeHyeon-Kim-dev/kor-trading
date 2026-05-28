from collections.abc import Iterable
from datetime import date

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market


class FakeMarketSnapshotProvider:
    """In-memory 가짜 MarketSnapshotProvider — 유스케이스 단위 테스트용."""

    def __init__(self) -> None:
        self._snapshots: list[StockSnapshot] = []

    def add(self, snapshot: StockSnapshot) -> None:
        self._snapshots.append(snapshot)

    def add_many(self, snapshots: Iterable[StockSnapshot]) -> None:
        self._snapshots.extend(snapshots)

    def clear(self) -> None:
        self._snapshots.clear()

    def get_market_snapshots(self, markets: tuple[Market, ...], as_of: date) -> list[StockSnapshot]:
        return [s for s in self._snapshots if s.ticker.market in markets and s.as_of == as_of]
