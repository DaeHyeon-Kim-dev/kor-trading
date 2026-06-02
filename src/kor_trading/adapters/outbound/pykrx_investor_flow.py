"""pykrx 기반 InvestorFlowProvider 어댑터.

pykrx.stock.get_market_net_purchases_of_equities(start, end, market, investor)
는 시장 전종목의 누적 순매수를 한 번에 반환. 시장 * 투자자 * (5d/20d) = 8 호출/주기.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from kor_trading.domain.ports.investor_flow_provider import InvestorFlow

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.ticker import Market


log = structlog.get_logger()

# pykrx 영업일 ≈ 캘린더일 * 1.4. 5영업일 ≈ 7일, 20영업일 ≈ 30일. 넉넉히.
_FIVE_DAY_LOOKBACK_CAL = 10
_TWENTY_DAY_LOOKBACK_CAL = 35
_NET_VALUE_COL = "순매수거래대금"
_FOREIGN = "외국인"
_INSTITUTION = "기관합계"


class _PykrxFlowModule(Protocol):
    def get_market_net_purchases_of_equities(
        self, start_date: str, end_date: str, market: str, investor: str
    ) -> Any: ...


def _default_module() -> _PykrxFlowModule:  # pragma: no cover
    from pykrx import stock  # noqa: PLC0415

    return stock  # type: ignore[no-any-return]


class PykrxInvestorFlowProvider:
    def __init__(self, stock_module: _PykrxFlowModule | None = None) -> None:
        self._stock = stock_module if stock_module is not None else _default_module()

    def get_flows(self, markets: tuple[Market, ...], as_of: date) -> dict[str, InvestorFlow]:
        end = as_of.strftime("%Y%m%d")
        start_5d = (as_of - timedelta(days=_FIVE_DAY_LOOKBACK_CAL)).strftime("%Y%m%d")
        start_20d = (as_of - timedelta(days=_TWENTY_DAY_LOOKBACK_CAL)).strftime("%Y%m%d")

        # ticker_code → (f5d, f20d, i5d, i20d) 누적
        acc: dict[str, list[int | None]] = {}

        for market in markets:
            calls = (
                (start_5d, _FOREIGN, 0),
                (start_20d, _FOREIGN, 1),
                (start_5d, _INSTITUTION, 2),
                (start_20d, _INSTITUTION, 3),
            )
            for start, investor, idx in calls:
                df = self._safe_fetch(start, end, market, investor)
                if df is None:
                    continue
                for ticker_code, row in df.iterrows():
                    code = str(ticker_code).zfill(6)
                    if code not in acc:
                        acc[code] = [None, None, None, None]
                    try:
                        acc[code][idx] = int(row[_NET_VALUE_COL])
                    except (KeyError, ValueError, TypeError):
                        continue

        return {
            code: InvestorFlow(
                foreign_net_5d=v[0],
                foreign_net_20d=v[1],
                institution_net_5d=v[2],
                institution_net_20d=v[3],
            )
            for code, v in acc.items()
        }

    def _safe_fetch(self, start: str, end: str, market: str, investor: str) -> Any:
        try:
            df = self._stock.get_market_net_purchases_of_equities(start, end, market, investor)
            if df is None or df.empty:
                return None
            return df
        except Exception as e:
            log.error(
                "pykrx.flow_fetch_failed",
                start=start,
                end=end,
                market=market,
                investor=investor,
                error=str(e),
            )
            return None
