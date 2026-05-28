"""FinanceDataReader 기반 TickerNameResolver.

fdr.StockListing("KRX") 한 번 호출로 전종목 매핑을 in-memory 캐시.
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Protocol

import structlog

log = structlog.get_logger()


class _FdrModule(Protocol):
    def StockListing(self, market: str) -> Any: ...


def _default_module() -> _FdrModule:  # pragma: no cover
    import FinanceDataReader as fdr  # noqa: PLC0415

    return fdr  # type: ignore[no-any-return]


# StockListing("KRX") DataFrame의 ticker 코드 컬럼 후보 (라이브러리 버전에 따라 다름)
_CODE_COLUMN_CANDIDATES = ("Code", "Symbol", "ticker", "단축코드")
_NAME_COLUMN_CANDIDATES = ("Name", "name", "종목명")


class FinanceDataReaderNameResolver:
    """fdr.StockListing("KRX") 결과를 첫 호출 시 캐시. 이후 in-memory lookup."""

    def __init__(self, fdr_module: _FdrModule | None = None) -> None:
        self._fdr = fdr_module if fdr_module is not None else _default_module()
        self._cache: dict[str, str] = {}
        self._loaded = False
        self._lock = Lock()

    def get_name(self, ticker_code: str) -> str | None:
        if not self._loaded:
            self._load()
        return self._cache.get(ticker_code)

    def _load(self) -> None:
        with self._lock:
            if self._loaded:  # pragma: no cover (race condition double-check)
                return
            try:
                df = self._fdr.StockListing("KRX")
            except Exception as e:
                log.error("fdr.stocklisting_failed", error=str(e))
                self._loaded = True  # 실패해도 재시도 폭주 회피
                return

            if df is None or df.empty:
                log.warning("fdr.stocklisting_empty")
                self._loaded = True
                return

            code_col = _first_present(df.columns, _CODE_COLUMN_CANDIDATES)
            name_col = _first_present(df.columns, _NAME_COLUMN_CANDIDATES)
            if code_col is None or name_col is None:
                log.error(
                    "fdr.unknown_columns",
                    columns=list(df.columns),
                    expected_code=_CODE_COLUMN_CANDIDATES,
                    expected_name=_NAME_COLUMN_CANDIDATES,
                )
                self._loaded = True
                return

            for _, row in df.iterrows():
                code = str(row[code_col]).zfill(6)
                name = str(row[name_col]).strip()
                if code and name:
                    self._cache[code] = name
            self._loaded = True
            log.info("fdr.loaded", count=len(self._cache))


def _first_present(columns: Any, candidates: tuple[str, ...]) -> str | None:
    col_set = set(columns)
    for c in candidates:
        if c in col_set:
            return c
    return None
