from dataclasses import dataclass
from typing import Literal, get_args

Market = Literal["KOSPI", "KOSDAQ"]

TICKER_CODE_LENGTH = 6


@dataclass(frozen=True, slots=True)
class Ticker:
    code: str
    name: str
    market: Market

    def __post_init__(self) -> None:
        if not (len(self.code) == TICKER_CODE_LENGTH and self.code.isdigit()):
            raise ValueError(
                f"invalid ticker code ({TICKER_CODE_LENGTH} digits required): {self.code!r}"
            )
        if not self.name.strip():
            raise ValueError("ticker name must not be blank")
        if self.market not in get_args(Market):
            raise ValueError(f"invalid market (KOSPI|KOSDAQ): {self.market!r}")
