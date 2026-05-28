"""PykrxOhlcvProvider 단위 테스트 (fake pykrx 모듈)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from kor_trading.adapters.outbound.pykrx_ohlcv import PykrxOhlcvProvider
from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider


class _FakePykrxStock:
    def __init__(
        self, df_by_ticker: dict[str, pd.DataFrame] | None = None, raise_for: str | None = None
    ) -> None:
        self._df = df_by_ticker or {}
        self._raise_for = raise_for

    def get_market_ohlcv_by_date(self, from_date: str, to_date: str, ticker: str) -> Any:
        _ = (from_date, to_date)
        if ticker == self._raise_for:
            raise RuntimeError("network down")
        return self._df.get(ticker, pd.DataFrame())


def _ohlcv_df(dates: list[date], close: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "시가": [close] * len(dates),
            "고가": [close + 100] * len(dates),
            "저가": [close - 100] * len(dates),
            "종가": [close] * len(dates),
            "거래량": [1000] * len(dates),
            "거래대금": [close * 1000] * len(dates),
        },
        index=pd.DatetimeIndex(dates, name="날짜"),
    )


class TestNormalFetch:
    def test_converts_dataframe_to_ohlcv_bars(self) -> None:
        bars_dates = [date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)]
        fake = _FakePykrxStock(df_by_ticker={"005930": _ohlcv_df(bars_dates)})
        provider = PykrxOhlcvProvider(stock_module=fake)

        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 30)
        assert len(bars) == 3
        assert bars[-1].close == 100
        assert bars[-1].date == date(2026, 5, 26)

    def test_returns_last_n_bars(self) -> None:
        bars_dates = [date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)]
        fake = _FakePykrxStock(df_by_ticker={"005930": _ohlcv_df(bars_dates)})
        provider = PykrxOhlcvProvider(stock_module=fake)

        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 2)
        assert len(bars) == 2


class TestErrors:
    def test_zero_days_returns_empty(self) -> None:
        provider = PykrxOhlcvProvider(stock_module=_FakePykrxStock())
        assert provider.get_daily_bars("005930", date(2026, 5, 26), 0) == []

    def test_fetch_exception_returns_empty(self) -> None:
        fake = _FakePykrxStock(raise_for="005930")
        provider = PykrxOhlcvProvider(stock_module=fake)
        assert provider.get_daily_bars("005930", date(2026, 5, 26), 30) == []

    def test_empty_dataframe_returns_empty(self) -> None:
        provider = PykrxOhlcvProvider(stock_module=_FakePykrxStock())
        assert provider.get_daily_bars("000000", date(2026, 5, 26), 30) == []


class TestSkipInvalidRows:
    def test_skips_negative_values(self) -> None:
        bars_dates = [date(2026, 5, 25), date(2026, 5, 26)]
        df = _ohlcv_df(bars_dates)
        df.iloc[0, df.columns.get_loc("종가")] = -1  # 음수로 변조
        fake = _FakePykrxStock(df_by_ticker={"005930": df})
        provider = PykrxOhlcvProvider(stock_module=fake)
        bars = provider.get_daily_bars("005930", date(2026, 5, 26), 30)
        assert len(bars) == 1  # 음수 행 skip


class TestProtocolConformance:
    def test_implements_ohlcv_provider(self) -> None:
        provider = PykrxOhlcvProvider(stock_module=_FakePykrxStock())
        assert isinstance(provider, OhlcvProvider)
