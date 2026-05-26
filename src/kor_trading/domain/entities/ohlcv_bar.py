from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class OhlcvBar:
    date: date
    open: int
    high: int
    low: int
    close: int
    volume: int
    trading_value: int

    def __post_init__(self) -> None:
        for field, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
            ("volume", self.volume),
            ("trading_value", self.trading_value),
        ):
            if value < 0:
                raise ValueError(f"{field} must be non-negative: {value}")
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
