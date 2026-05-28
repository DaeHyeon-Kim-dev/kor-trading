"""pykrx 기반 MarketSnapshotProvider 어댑터.

도메인 포트 `MarketSnapshotProvider`를 구현해, KRX 시장 전체 종목 스냅샷을
`StockSnapshot` 리스트로 반환한다. 도메인은 pandas/pykrx를 모른다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import structlog

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market, Ticker

if TYPE_CHECKING:
    from datetime import date


log = structlog.get_logger()


class _PykrxStockModule(Protocol):
    """pykrx.stock 모듈에서 사용하는 함수만 모은 작은 인터페이스 — DI 가능."""

    def get_market_ohlcv(self, date: str, market: str = "KOSPI") -> Any: ...

    def get_market_cap(self, date: str, market: str = "KOSPI") -> Any: ...


def _default_stock_module() -> _PykrxStockModule:  # pragma: no cover
    # Lazy import: pykrx 로드는 무거움 + DI로 단위 테스트는 fake 사용
    from pykrx import stock  # noqa: PLC0415

    return stock  # type: ignore[no-any-return]


class PykrxMarketSnapshotProvider:
    """KRX 데이터 fetch → StockSnapshot 리스트로 변환."""

    def __init__(self, stock_module: _PykrxStockModule | None = None) -> None:
        self._stock = stock_module if stock_module is not None else _default_stock_module()

    def get_market_snapshots(self, markets: tuple[Market, ...], as_of: date) -> list[StockSnapshot]:
        date_str = as_of.strftime("%Y%m%d")
        snapshots: list[StockSnapshot] = []
        for market in markets:
            try:
                snapshots.extend(self._fetch_market(market, date_str, as_of))
            except Exception as e:  # 한 시장 실패가 전체를 막지 않도록
                log.error(
                    "pykrx.fetch_failed",
                    market=market,
                    date=date_str,
                    error=str(e),
                )
        return snapshots

    def _fetch_market(self, market: Market, date_str: str, as_of: date) -> list[StockSnapshot]:
        ohlcv_df = self._stock.get_market_ohlcv(date_str, market=market)
        cap_df = self._stock.get_market_cap(date_str, market=market)
        if ohlcv_df is None or ohlcv_df.empty or cap_df is None or cap_df.empty:
            log.warning("pykrx.empty_market", market=market, date=date_str)
            return []

        snapshots: list[StockSnapshot] = []
        for ticker_code, row in ohlcv_df.iterrows():
            code = str(ticker_code)
            if code not in cap_df.index:
                continue
            cap_row = cap_df.loc[code]
            try:
                ticker = Ticker(code=code, name=code, market=market)
                snap = StockSnapshot(
                    ticker=ticker,
                    as_of=as_of,
                    close=int(row["종가"]),
                    change_pct=float(row["등락률"]),
                    volume=int(row["거래량"]),
                    trading_value=int(row["거래대금"]),
                    market_cap=int(cap_row["시가총액"]),
                )
                snapshots.append(snap)
            except (ValueError, KeyError) as e:
                log.warning(
                    "pykrx.skip_ticker",
                    ticker=code,
                    market=market,
                    error=str(e),
                )
        return snapshots
