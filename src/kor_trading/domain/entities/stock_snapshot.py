from dataclasses import dataclass
from datetime import date

from kor_trading.domain.entities.ticker import Ticker


@dataclass(frozen=True, slots=True)
class StockSnapshot:
    ticker: Ticker
    as_of: date
    close: int
    change_pct: float
    volume: int
    trading_value: int
    market_cap: int

    def __post_init__(self) -> None:
        for field, value in (
            ("close", self.close),
            ("volume", self.volume),
            ("trading_value", self.trading_value),
            ("market_cap", self.market_cap),
        ):
            if value < 0:
                raise ValueError(f"{field} must be non-negative: {value}")
