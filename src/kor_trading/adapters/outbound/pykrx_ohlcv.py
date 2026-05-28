"""pykrx 기반 OhlcvProvider 어댑터.

pykrx.stock.get_market_ohlcv_by_date → DataFrame → list[OhlcvBar].
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from kor_trading.domain.entities.ohlcv_bar import OhlcvBar

if TYPE_CHECKING:
    from datetime import date


log = structlog.get_logger()


class _PykrxStockOhlcvModule(Protocol):
    def get_market_ohlcv_by_date(self, from_date: str, to_date: str, ticker: str) -> Any: ...


def _default_module() -> _PykrxStockOhlcvModule:  # pragma: no cover
    from pykrx import stock  # noqa: PLC0415

    return stock  # type: ignore[no-any-return]


class PykrxOhlcvProvider:
    """과거 일봉 시계열을 pykrx로 fetch."""

    def __init__(
        self,
        stock_module: _PykrxStockOhlcvModule | None = None,
        history_buffer_factor: float = 1.6,
    ) -> None:
        """history_buffer_factor: 휴장일 보정. days * factor만큼 거슬러 fetch."""
        self._stock = stock_module if stock_module is not None else _default_module()
        self._buffer = history_buffer_factor

    def get_daily_bars(self, ticker_code: str, end_date: date, days: int) -> list[OhlcvBar]:
        if days <= 0:
            return []
        start_date = end_date - timedelta(days=int(days * self._buffer) + 7)
        from_str = start_date.strftime("%Y%m%d")
        to_str = end_date.strftime("%Y%m%d")
        try:
            df = self._stock.get_market_ohlcv_by_date(from_str, to_str, ticker_code)
        except Exception as e:
            log.error("pykrx_ohlcv.fetch_failed", ticker=ticker_code, error=str(e))
            return []

        if df is None or df.empty:
            return []

        bars: list[OhlcvBar] = []
        for idx, row in df.iterrows():
            try:
                bars.append(
                    OhlcvBar(
                        date=_to_date(idx),
                        open=int(row["시가"]),
                        high=int(row["고가"]),
                        low=int(row["저가"]),
                        close=int(row["종가"]),
                        volume=int(row["거래량"]),
                        trading_value=int(row.get("거래대금", 0)),
                    )
                )
            except (ValueError, KeyError) as e:
                log.warning("pykrx_ohlcv.skip_row", ticker=ticker_code, date=str(idx), error=str(e))
        return bars[-days:]


def _to_date(idx: Any) -> date:
    # pandas Timestamp or python date
    if hasattr(idx, "date"):
        return idx.date()  # type: ignore[no-any-return]
    return idx  # type: ignore[no-any-return]  # pragma: no cover (pandas index is always Timestamp here)
