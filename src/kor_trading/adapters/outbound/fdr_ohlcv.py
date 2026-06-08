"""FinanceDataReader 기반 OhlcvProvider.

`fdr.DataReader(code, start, end)` → 일봉 시계열 → list[OhlcvBar].
개별종목 시계열을 1회 호출로 받아 효율적이며 로그인이 필요 없다.
거래대금은 DataReader가 제공하지 않으므로 0으로 둔다 (지표 계산 미사용 — OBV는 volume만).

KRX 일별매매정보는 "날짜별 전종목"이라 개별 종목 시계열엔 호출이 폭증하므로
시계열 조회는 FDR을 사용한다. (종목 선정 스냅샷은 KRX OPEN API 사용)
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from kor_trading.domain.entities.ohlcv_bar import OhlcvBar

if TYPE_CHECKING:
    from datetime import date

log = structlog.get_logger()

_BUFFER_FACTOR = 1.6
_BUFFER_EXTRA_DAYS = 7


class _FdrModule(Protocol):
    def DataReader(self, symbol: str, start: str, end: str) -> Any: ...


def _default_module() -> _FdrModule:  # pragma: no cover
    import FinanceDataReader as fdr  # noqa: PLC0415

    return fdr  # type: ignore[no-any-return]


class FdrOhlcvProvider:
    def __init__(self, fdr_module: _FdrModule | None = None) -> None:
        self._fdr = fdr_module if fdr_module is not None else _default_module()

    def get_daily_bars(self, ticker_code: str, end_date: date, days: int) -> list[OhlcvBar]:
        if days <= 0:
            return []
        start = end_date - timedelta(days=int(days * _BUFFER_FACTOR) + _BUFFER_EXTRA_DAYS)
        try:
            df = self._fdr.DataReader(
                ticker_code, start.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
            )
        except Exception as e:
            log.error("fdr_ohlcv.fetch_failed", ticker=ticker_code, error=str(e))
            return []

        if df is None or df.empty:
            return []

        bars: list[OhlcvBar] = []
        for idx, row in df.iterrows():
            try:
                bars.append(
                    OhlcvBar(
                        date=_to_date(idx),
                        open=_int(row["Open"]),
                        high=_int(row["High"]),
                        low=_int(row["Low"]),
                        close=_int(row["Close"]),
                        volume=_int(row["Volume"]),
                        trading_value=0,
                    )
                )
            except (ValueError, KeyError, TypeError) as e:
                log.warning("fdr_ohlcv.skip_row", ticker=ticker_code, error=str(e))
        return bars[-days:]


def _to_date(idx: Any) -> date:
    if hasattr(idx, "date"):
        return idx.date()  # type: ignore[no-any-return]
    return idx  # type: ignore[no-any-return]  # pragma: no cover


def _int(value: Any) -> int:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError("missing numeric value")
    return int(value)
