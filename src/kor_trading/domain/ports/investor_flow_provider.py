"""투자자별 수급(외국인/기관 누적 순매수) fetch 포트."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.ticker import Market


@dataclass(frozen=True, slots=True)
class InvestorFlow:
    """한 종목의 외국인·기관 누적 순매수(원, 거래대금 기준)."""

    foreign_net_5d: int | None = None
    foreign_net_20d: int | None = None
    institution_net_5d: int | None = None
    institution_net_20d: int | None = None


@runtime_checkable
class InvestorFlowProvider(Protocol):
    """시장 단위로 batch fetch — 종목당 호출이 아니라 시장당 호출.

    반환: {ticker_code: InvestorFlow}
    """

    def get_flows(self, markets: tuple[Market, ...], as_of: date) -> dict[str, InvestorFlow]: ...
