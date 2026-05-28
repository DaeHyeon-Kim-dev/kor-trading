"""FinanceDataReaderNameResolver 테스트."""

from __future__ import annotations

from typing import Any

import pandas as pd

from kor_trading.adapters.outbound.fdr_ticker_name_resolver import (
    FinanceDataReaderNameResolver,
)
from kor_trading.domain.ports.ticker_name_resolver import TickerNameResolver


class _FakeFdr:
    def __init__(
        self,
        df: pd.DataFrame | None = None,
        raise_error: bool = False,
    ) -> None:
        self._df = df
        self._raise = raise_error
        self.calls = 0

    def StockListing(self, market: str) -> Any:
        _ = market
        self.calls += 1
        if self._raise:
            raise RuntimeError("network down")
        return self._df


def _df_code_name() -> pd.DataFrame:
    return pd.DataFrame({"Code": ["005930", "035720"], "Name": ["삼성전자", "카카오"]})


def _df_symbol_name() -> pd.DataFrame:
    return pd.DataFrame({"Symbol": ["005930"], "Name": ["삼성전자"]})


class TestResolve:
    def test_returns_korean_name_for_known_ticker(self) -> None:
        fake = _FakeFdr(df=_df_code_name())
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") == "삼성전자"
        assert r.get_name("035720") == "카카오"

    def test_returns_none_for_unknown_ticker(self) -> None:
        fake = _FakeFdr(df=_df_code_name())
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("999999") is None

    def test_caches_after_first_load(self) -> None:
        fake = _FakeFdr(df=_df_code_name())
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        r.get_name("005930")
        r.get_name("035720")
        r.get_name("999999")
        assert fake.calls == 1  # StockListing은 1번만 호출

    def test_supports_symbol_column_alternate(self) -> None:
        fake = _FakeFdr(df=_df_symbol_name())
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") == "삼성전자"


class TestFailureHandling:
    def test_fdr_exception_returns_none_silently(self) -> None:
        fake = _FakeFdr(raise_error=True)
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") is None
        # 재시도 폭주 방지: 다시 호출해도 fdr는 다시 호출 안 됨
        r.get_name("035720")
        assert fake.calls == 1

    def test_empty_dataframe_returns_none(self) -> None:
        fake = _FakeFdr(df=pd.DataFrame())
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") is None

    def test_unknown_columns_returns_none(self) -> None:
        fake = _FakeFdr(df=pd.DataFrame({"foo": ["x"]}))
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") is None


class TestZeroPaddedCodes:
    def test_pads_short_codes_to_six_digits(self) -> None:
        df = pd.DataFrame({"Code": ["5930"], "Name": ["삼성전자"]})
        fake = _FakeFdr(df=df)
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") == "삼성전자"

    def test_skips_rows_with_empty_name(self) -> None:
        df = pd.DataFrame({"Code": ["005930", "035720"], "Name": ["삼성전자", "   "]})
        fake = _FakeFdr(df=df)
        r = FinanceDataReaderNameResolver(fdr_module=fake)
        assert r.get_name("005930") == "삼성전자"
        assert r.get_name("035720") is None  # 빈 이름 → skip → 매핑 없음


class TestProtocolConformance:
    def test_conforms_to_ticker_name_resolver(self) -> None:
        r = FinanceDataReaderNameResolver(fdr_module=_FakeFdr())
        assert isinstance(r, TickerNameResolver)
