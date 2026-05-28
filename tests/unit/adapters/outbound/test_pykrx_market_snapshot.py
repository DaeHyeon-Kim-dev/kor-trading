"""PykrxMarketSnapshotProvider 단위 테스트.

실제 pykrx 호출 없이 DI한 가짜 모듈로 동작 검증.
통합 테스트(실 네트워크)는 tests/integration/에 별도.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from kor_trading.adapters.outbound.pykrx_market_snapshot import PykrxMarketSnapshotProvider
from kor_trading.domain.ports.market_snapshot_provider import MarketSnapshotProvider

AS_OF = date(2026, 5, 26)


class _FakePykrxStock:
    """pykrx.stock 모듈의 함수 시그니처만 모방."""

    def __init__(
        self,
        *,
        ohlcv: dict[str, pd.DataFrame] | None = None,
        cap: dict[str, pd.DataFrame] | None = None,
        raise_for_market: str | None = None,
    ) -> None:
        self._ohlcv = ohlcv or {}
        self._cap = cap or {}
        self._raise_for_market = raise_for_market

    def get_market_ohlcv(self, date: str, market: str = "KOSPI") -> Any:
        _ = date
        if market == self._raise_for_market:
            raise RuntimeError("network down")
        return self._ohlcv.get(market, pd.DataFrame())

    def get_market_cap(self, date: str, market: str = "KOSPI") -> Any:
        _ = date
        return self._cap.get(market, pd.DataFrame())


def _ohlcv_df(rows: list[tuple[str, int, float, int, int]]) -> pd.DataFrame:
    """rows: (ticker, 종가, 등락률, 거래량, 거래대금)"""
    return pd.DataFrame(
        {
            "시가": [0] * len(rows),
            "고가": [0] * len(rows),
            "저가": [0] * len(rows),
            "종가": [r[1] for r in rows],
            "거래량": [r[3] for r in rows],
            "거래대금": [r[4] for r in rows],
            "등락률": [r[2] for r in rows],
        },
        index=[r[0] for r in rows],
    )


def _cap_df(rows: list[tuple[str, int]]) -> pd.DataFrame:
    """rows: (ticker, 시가총액)"""
    return pd.DataFrame(
        {"시가총액": [r[1] for r in rows]},
        index=[r[0] for r in rows],
    )


class TestNormalFetch:
    def test_returns_snapshots_for_each_ticker(self) -> None:
        fake = _FakePykrxStock(
            ohlcv={"KOSPI": _ohlcv_df([("005930", 78500, 5.2, 25_300_000, 1_980_000_000_000)])},
            cap={"KOSPI": _cap_df([("005930", 469_000_000_000_000)])},
        )
        provider = PykrxMarketSnapshotProvider(stock_module=fake)

        snapshots = provider.get_market_snapshots(("KOSPI",), AS_OF)

        assert len(snapshots) == 1
        s = snapshots[0]
        assert s.ticker.code == "005930"
        assert s.ticker.market == "KOSPI"
        assert s.close == 78500
        assert s.change_pct == 5.2
        assert s.volume == 25_300_000
        assert s.trading_value == 1_980_000_000_000
        assert s.market_cap == 469_000_000_000_000

    def test_concatenates_markets(self) -> None:
        fake = _FakePykrxStock(
            ohlcv={
                "KOSPI": _ohlcv_df([("005930", 78500, 5.2, 1, 1_000)]),
                "KOSDAQ": _ohlcv_df([("035720", 50000, -3.1, 1, 1_000)]),
            },
            cap={
                "KOSPI": _cap_df([("005930", 469_000_000_000_000)]),
                "KOSDAQ": _cap_df([("035720", 20_000_000_000_000)]),
            },
        )
        provider = PykrxMarketSnapshotProvider(stock_module=fake)

        snapshots = provider.get_market_snapshots(("KOSPI", "KOSDAQ"), AS_OF)
        codes = {s.ticker.code for s in snapshots}
        assert codes == {"005930", "035720"}
        markets = {s.ticker.market for s in snapshots}
        assert markets == {"KOSPI", "KOSDAQ"}


class TestHolidayOrEmptyMarket:
    def test_empty_ohlcv_returns_empty_list(self) -> None:
        fake = _FakePykrxStock(ohlcv={"KOSPI": pd.DataFrame()})
        provider = PykrxMarketSnapshotProvider(stock_module=fake)
        assert provider.get_market_snapshots(("KOSPI",), AS_OF) == []


class TestFailureIsolation:
    def test_market_failure_does_not_block_others(self) -> None:
        fake = _FakePykrxStock(
            ohlcv={"KOSDAQ": _ohlcv_df([("035720", 50000, -3.1, 1, 1_000)])},
            cap={"KOSDAQ": _cap_df([("035720", 20_000_000_000_000)])},
            raise_for_market="KOSPI",
        )
        provider = PykrxMarketSnapshotProvider(stock_module=fake)

        snapshots = provider.get_market_snapshots(("KOSPI", "KOSDAQ"), AS_OF)
        assert [s.ticker.code for s in snapshots] == ["035720"]


class TestSkipInvalidRows:
    def test_skips_ticker_missing_in_cap(self) -> None:
        fake = _FakePykrxStock(
            ohlcv={
                "KOSPI": _ohlcv_df(
                    [
                        ("005930", 78500, 5.2, 1, 1_000),
                        ("000000", 1000, 0.0, 1, 1_000),  # cap에 없음
                    ]
                )
            },
            cap={"KOSPI": _cap_df([("005930", 469_000_000_000_000)])},
        )
        provider = PykrxMarketSnapshotProvider(stock_module=fake)

        snapshots = provider.get_market_snapshots(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in snapshots] == ["005930"]

    def test_skips_negative_values(self) -> None:
        # 도메인 검증(StockSnapshot 비음수)이 raise → skip
        fake = _FakePykrxStock(
            ohlcv={
                "KOSPI": _ohlcv_df(
                    [
                        ("005930", 78500, 5.2, 1, 1_000),
                        ("005931", -1, 0.0, 1, 1_000),  # close 음수 → skip
                    ]
                )
            },
            cap={
                "KOSPI": _cap_df(
                    [
                        ("005930", 469_000_000_000_000),
                        ("005931", 1_000_000_000_000),
                    ]
                )
            },
        )
        provider = PykrxMarketSnapshotProvider(stock_module=fake)

        snapshots = provider.get_market_snapshots(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in snapshots] == ["005930"]


class TestProtocolConformance:
    def test_provider_implements_market_snapshot_provider_port(self) -> None:
        fake = _FakePykrxStock()
        provider = PykrxMarketSnapshotProvider(stock_module=fake)
        assert isinstance(provider, MarketSnapshotProvider)
