"""KRX OPEN API 기반 MarketSnapshotProvider.

일별매매정보(유가/코스닥)로 당일 전종목 스냅샷을 만든다.
종목명·시가총액까지 응답에 포함되어 별도 resolver가 필요 없다.

요청 as_of가 휴장일/미래면 가장 최근 영업일까지 거슬러 탐색한다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import TICKER_CODE_LENGTH, Market, Ticker

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.adapters.outbound.krx_openapi_client import KrxOpenApiClient

log = structlog.get_logger()

_MAX_LOOKBACK_DAYS = 10  # 휴장일 연휴 대비

_COL_CODE = "ISU_CD"
_COL_NAME = "ISU_NM"
_COL_CLOSE = "TDD_CLSPRC"
_COL_CHANGE_RT = "FLUC_RT"
_COL_VOLUME = "ACC_TRDVOL"
_COL_AMOUNT = "ACC_TRDVAL"
_COL_MARCAP = "MKTCAP"


class KrxOpenApiMarketSnapshotProvider:
    def __init__(self, client: KrxOpenApiClient) -> None:
        self._client = client

    def get_market_snapshots(self, markets: tuple[Market, ...], as_of: date) -> list[StockSnapshot]:
        snapshots: list[StockSnapshot] = []
        for market in markets:
            rows, trade_date = self._fetch_latest(market, as_of)
            if not rows:
                log.warning("krx_snapshot.no_data", market=market, as_of=as_of.isoformat())
                continue
            for row in rows:
                snap = _row_to_snapshot(row, market, trade_date)
                if snap is not None:
                    snapshots.append(snap)
        return snapshots

    def _fetch_latest(self, market: Market, as_of: date) -> tuple[list[dict[str, Any]], date]:
        """as_of부터 거슬러 데이터가 있는 첫 영업일을 찾아 반환."""
        for back in range(_MAX_LOOKBACK_DAYS + 1):
            d = as_of - timedelta(days=back)
            rows = self._client.get_daily_trades(market, d.strftime("%Y%m%d"))
            if rows:
                if back > 0:
                    log.info(
                        "krx_snapshot.adjusted_date",
                        market=market,
                        requested=as_of.isoformat(),
                        actual=d.isoformat(),
                    )
                return rows, d
        return [], as_of


def _row_to_snapshot(row: dict[str, Any], market: Market, trade_date: date) -> StockSnapshot | None:
    code = str(row.get(_COL_CODE, "")).strip()
    if not (len(code) == TICKER_CODE_LENGTH and code.isdigit()):
        return None
    name = str(row.get(_COL_NAME, "")).strip() or code
    try:
        return StockSnapshot(
            ticker=Ticker(code=code, name=name, market=market),
            as_of=trade_date,
            close=_int(row.get(_COL_CLOSE)),
            change_pct=_float(row.get(_COL_CHANGE_RT)),
            volume=_int(row.get(_COL_VOLUME)),
            trading_value=_int(row.get(_COL_AMOUNT)),
            market_cap=_int(row.get(_COL_MARCAP)),
        )
    except (ValueError, TypeError):
        return None


def _int(value: Any) -> int:
    if value is None:
        raise ValueError("missing int")
    s = str(value).strip().replace(",", "")
    if not s or s == "-":
        raise ValueError("empty int")
    return int(float(s))


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    s = str(value).strip().replace(",", "")
    if not s or s == "-":
        return 0.0
    return float(s)
