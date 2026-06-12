"""MarketOverview / summarize_market 테스트 (PRD R2)."""

from __future__ import annotations

from datetime import date

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market, Ticker
from kor_trading.domain.values.market_overview import (
    MarketBreadth,
    MarketOverview,
    overall_regime,
    summarize_market,
)

AS_OF = date(2026, 6, 9)

_CODES = iter(f"{i:06d}" for i in range(1, 999))


def _snap(market: Market, change_pct: float, trading_value: int = 1_000_000_000) -> StockSnapshot:
    return StockSnapshot(
        ticker=Ticker(code=next(_CODES), name="X", market=market),
        as_of=AS_OF,
        close=10_000,
        change_pct=change_pct,
        volume=100_000,
        trading_value=trading_value,
        market_cap=1_000_000_000_000,
    )


class TestSummarizeMarket:
    def test_empty_universe_no_breadths(self) -> None:
        assert summarize_market([]).breadths == ()

    def test_counts_advancers_decliners_unchanged(self) -> None:
        snaps = [
            _snap("KOSPI", 1.0),
            _snap("KOSPI", -2.0),
            _snap("KOSPI", 0.0),
            _snap("KOSPI", 3.0),
        ]
        ov = summarize_market(snaps)
        assert len(ov.breadths) == 1
        b = ov.breadths[0]
        assert b.market == "KOSPI"
        assert (b.total, b.advancers, b.decliners, b.unchanged) == (4, 2, 1, 1)

    def test_avg_change_and_total_value(self) -> None:
        snaps = [
            _snap("KOSDAQ", 1.0, trading_value=2_000_000_000),
            _snap("KOSDAQ", 3.0, trading_value=3_000_000_000),
        ]
        b = summarize_market(snaps).breadths[0]
        assert b.avg_change_pct == 2.0
        assert b.total_trading_value == 5_000_000_000

    def test_groups_per_market_in_first_seen_order(self) -> None:
        snaps = [_snap("KOSPI", 1.0), _snap("KOSDAQ", 1.0), _snap("KOSPI", -1.0)]
        markets = [b.market for b in summarize_market(snaps).breadths]
        assert markets == ["KOSPI", "KOSDAQ"]


class TestSentiment:
    def _breadth(self, up: int, down: int) -> MarketBreadth:
        return MarketBreadth(
            market="KOSPI",
            total=up + down,
            advancers=up,
            decliners=down,
            unchanged=0,
            avg_change_pct=0.0,
            total_trading_value=0,
        )

    def test_bullish_when_advancers_dominate(self) -> None:
        assert self._breadth(up=30, down=10).sentiment == "강세"

    def test_bearish_when_decliners_dominate(self) -> None:
        assert self._breadth(up=10, down=30).sentiment == "약세"

    def test_mixed_when_balanced(self) -> None:
        assert self._breadth(up=11, down=10).sentiment == "혼조"


class TestOverallRegime:
    def _ov(self, b: list[MarketBreadth]) -> MarketOverview:
        return MarketOverview(breadths=tuple(b))

    def _b(self, up: int, down: int) -> MarketBreadth:
        return MarketBreadth("KOSPI", up + down, up, down, 0, 0.0, 0)

    def test_empty_is_mixed(self) -> None:
        assert overall_regime(self._ov([])) == "혼조"

    def test_bullish_aggregate(self) -> None:
        ov = self._ov([self._b(300, 100), self._b(200, 50)])
        assert overall_regime(ov) == "강세"

    def test_bearish_aggregate(self) -> None:
        ov = self._ov([self._b(50, 200), self._b(40, 150)])
        assert overall_regime(ov) == "약세"

    def test_mixed_aggregate(self) -> None:
        ov = self._ov([self._b(100, 90)])
        assert overall_regime(ov) == "혼조"
