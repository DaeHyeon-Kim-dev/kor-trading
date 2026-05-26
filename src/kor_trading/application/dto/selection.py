from dataclasses import dataclass, field
from datetime import date

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market

VALID_SELECTION_REASONS: frozenset[str] = frozenset({"top_volume", "surge", "plunge"})


@dataclass(frozen=True, slots=True)
class SelectionCriteria:
    top_volume_n: int = 50
    surge_top_n: int = 10
    plunge_top_n: int = 10
    market_cap_min_krw: int = 50_000_000_000
    max_candidates: int = 30
    markets: tuple[Market, ...] = ("KOSPI", "KOSDAQ")

    def __post_init__(self) -> None:
        for field_name, value in (
            ("top_volume_n", self.top_volume_n),
            ("surge_top_n", self.surge_top_n),
            ("plunge_top_n", self.plunge_top_n),
            ("market_cap_min_krw", self.market_cap_min_krw),
        ):
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative: {value}")
        if self.max_candidates <= 0:
            raise ValueError(f"max_candidates must be positive: {self.max_candidates}")
        if not self.markets:
            raise ValueError("markets must not be empty")


@dataclass(frozen=True, slots=True)
class SelectionCandidate:
    snapshot: StockSnapshot
    selection_reasons: tuple[str, ...]
    rank_by_volume: int | None
    rank_by_change_up: int | None
    rank_by_change_down: int | None

    def __post_init__(self) -> None:
        if not self.selection_reasons:
            raise ValueError("at least one selection reason required")
        unknown = set(self.selection_reasons) - VALID_SELECTION_REASONS
        if unknown:
            raise ValueError(f"unknown selection reason(s): {sorted(unknown)}")


@dataclass(frozen=True, slots=True)
class SelectionResult:
    as_of: date
    total_screened: int
    candidates: tuple[SelectionCandidate, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.total_screened < 0:
            raise ValueError(f"total_screened must be non-negative: {self.total_screened}")
