"""FdrOhlcvProvider 단위 테스트 (fake FDR 모듈)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from kor_trading.adapters.outbound.fdr_ohlcv import FdrOhlcvProvider
from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider


class _FakeFdr:
    def __init__(self, df: pd.DataFrame | None = None, raise_exc: bool = False) -> None:
        self._df = df
        self._raise = raise_exc
        self.calls: list[tuple[str, str, str]] = []

    def DataReader(self, symbol: str, start: str, end: str) -> Any:
        self.calls.append((symbol, start, end))
        if self._raise:
            raise RuntimeError("network down")
        return self._df


def _ohlcv_df(dates: list[date], close: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [close] * len(dates),
            "High": [close + 100] * len(dates),
            "Low": [close - 100] * len(dates),
            "Close": [close] * len(dates),
            "Volume": [1000] * len(dates),
            "Change": [0.0] * len(dates),
        },
        index=pd.DatetimeIndex(dates, name="Date"),
    )


class TestNormalFetch:
    def test_converts_to_bars(self) -> None:
        dates = [date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)]
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr(df=_ohlcv_df(dates)))
        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 30)
        assert len(bars) == 3
        assert bars[-1].close == 100
        assert bars[-1].trading_value == 0  # FDR 미제공
        assert bars[-1].date == date(2026, 5, 26)

    def test_returns_last_n(self) -> None:
        dates = [date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)]
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr(df=_ohlcv_df(dates)))
        assert len(provider.get_daily_bars("005930", date(2026, 5, 26), 2)) == 2


class TestEdgeCases:
    def test_zero_days_empty(self) -> None:
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr())
        assert provider.get_daily_bars("005930", date(2026, 5, 26), 0) == []

    def test_fetch_exception_empty(self) -> None:
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr(raise_exc=True))
        assert provider.get_daily_bars("005930", date(2026, 5, 26), 30) == []

    def test_empty_df_empty(self) -> None:
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr(df=pd.DataFrame()))
        assert provider.get_daily_bars("000000", date(2026, 5, 26), 30) == []

    def test_skips_negative_close(self) -> None:
        dates = [date(2026, 5, 25), date(2026, 5, 26)]
        df = _ohlcv_df(dates)
        df.iloc[0, df.columns.get_loc("Close")] = -1
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr(df=df))
        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 30)
        assert len(bars) == 1

    def test_skips_nan_value(self) -> None:
        dates = [date(2026, 5, 25), date(2026, 5, 26)]
        df = _ohlcv_df(dates)
        df.iloc[0, df.columns.get_loc("Volume")] = float("nan")
        provider = FdrOhlcvProvider(fdr_module=_FakeFdr(df=df))
        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 30)
        assert len(bars) == 1  # NaN 행 skip


class TestProtocolConformance:
    def test_conforms(self) -> None:
        assert isinstance(FdrOhlcvProvider(fdr_module=_FakeFdr()), OhlcvProvider)
