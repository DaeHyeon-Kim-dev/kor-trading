"""SelectStocksUseCase 테스트.

PRD: docs/PRD.md § 3.2 — 거래대금 Top 50 + 급등 Top 10 + 급락 Top 10 합집합,
시총 필터, max_candidates cap, ranks.
"""

from datetime import date

from kor_trading.application.dto.selection import SelectionCriteria
from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase
from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market, Ticker
from kor_trading.domain.ports.market_snapshot_provider import MarketSnapshotProvider
from tests.fakes.fake_market_snapshot_provider import FakeMarketSnapshotProvider

AS_OF = date(2026, 5, 26)


def _snap(
    code: str,
    *,
    name: str = "X",
    market: Market = "KOSPI",
    close: int = 10_000,
    change_pct: float = 0.0,
    volume: int = 100_000,
    trading_value: int = 1_000_000_000,
    market_cap: int = 1_000_000_000_000,
) -> StockSnapshot:
    return StockSnapshot(
        ticker=Ticker(code=code, name=name, market=market),
        as_of=AS_OF,
        close=close,
        change_pct=change_pct,
        volume=volume,
        trading_value=trading_value,
        market_cap=market_cap,
    )


def _make_uc(snapshots: list[StockSnapshot]) -> SelectStocksUseCase:
    provider = FakeMarketSnapshotProvider()
    provider.add_many(snapshots)
    return SelectStocksUseCase(market_snapshots=provider)


class TestEmptyMarket:
    def test_returns_empty_when_no_snapshots(self) -> None:
        uc = _make_uc([])
        result = uc.execute(SelectionCriteria(), as_of=AS_OF)
        assert result.candidates == ()
        assert result.total_screened == 0
        assert result.as_of == AS_OF


class TestTopVolume:
    def test_returns_top_n_sorted_by_trading_value_desc(self) -> None:
        snapshots = [_snap(f"00000{i}", trading_value=i * 1_000_000_000) for i in range(1, 6)]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=3, surge_top_n=0, plunge_top_n=0), as_of=AS_OF
        )
        codes = [c.snapshot.ticker.code for c in result.candidates]
        assert codes == ["000005", "000004", "000003"]
        assert result.candidates[0].rank_by_volume == 1
        assert result.candidates[1].rank_by_volume == 2
        assert "top_volume" in result.candidates[0].selection_reasons


class TestSurgeAndPlunge:
    def test_surge_picks_highest_change_pct(self) -> None:
        snapshots = [
            _snap("000001", change_pct=-5.0),
            _snap("000002", change_pct=+8.0),
            _snap("000003", change_pct=+3.0),
        ]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=0, surge_top_n=2, plunge_top_n=0), as_of=AS_OF
        )
        codes = [c.snapshot.ticker.code for c in result.candidates]
        assert codes == ["000002", "000003"]
        assert "surge" in result.candidates[0].selection_reasons
        assert result.candidates[0].rank_by_change_up == 1

    def test_plunge_picks_lowest_change_pct(self) -> None:
        snapshots = [
            _snap("000001", change_pct=-5.0),
            _snap("000002", change_pct=+8.0),
            _snap("000003", change_pct=-9.0),
        ]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=0, surge_top_n=0, plunge_top_n=2), as_of=AS_OF
        )
        codes = [c.snapshot.ticker.code for c in result.candidates]
        assert codes == ["000003", "000001"]
        assert "plunge" in result.candidates[0].selection_reasons
        assert result.candidates[0].rank_by_change_down == 1


class TestUnionAndDeduplication:
    def test_same_ticker_appears_only_once_with_combined_reasons(self) -> None:
        # 한 종목이 거래대금 + 급등 양쪽 다 충족
        snapshots = [
            _snap("000001", change_pct=+10.0, trading_value=10_000_000_000_000),
            _snap("000002", change_pct=+2.0, trading_value=1_000_000_000),
        ]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=1, surge_top_n=1, plunge_top_n=0), as_of=AS_OF
        )
        codes = [c.snapshot.ticker.code for c in result.candidates]
        assert codes.count("000001") == 1
        c = next(c for c in result.candidates if c.snapshot.ticker.code == "000001")
        assert set(c.selection_reasons) == {"top_volume", "surge"}
        assert c.rank_by_volume == 1
        assert c.rank_by_change_up == 1


class TestMarketCapFilter:
    def test_excludes_below_market_cap_min(self) -> None:
        snapshots = [
            _snap("000001", market_cap=10_000_000_000, trading_value=5_000_000_000_000),
            _snap("000002", market_cap=100_000_000_000, trading_value=1_000_000_000_000),
        ]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(
                top_volume_n=5,
                surge_top_n=0,
                plunge_top_n=0,
                market_cap_min_krw=50_000_000_000,
            ),
            as_of=AS_OF,
        )
        codes = [c.snapshot.ticker.code for c in result.candidates]
        assert codes == ["000002"]


class TestMaxCandidatesCap:
    def test_caps_total_candidates(self) -> None:
        snapshots = [_snap(f"00000{i}", trading_value=i * 1_000_000_000) for i in range(1, 10)]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=9, surge_top_n=0, plunge_top_n=0, max_candidates=3),
            as_of=AS_OF,
        )
        assert len(result.candidates) == 3


class TestMarketsFilter:
    def test_only_includes_requested_markets(self) -> None:
        snapshots = [
            _snap("000001", market="KOSPI", trading_value=5_000_000_000_000),
            _snap("000002", market="KOSDAQ", trading_value=10_000_000_000_000),
        ]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=5, surge_top_n=0, plunge_top_n=0, markets=("KOSPI",)),
            as_of=AS_OF,
        )
        codes = [c.snapshot.ticker.code for c in result.candidates]
        assert codes == ["000001"]


class TestTotalScreened:
    def test_reports_count_before_filtering(self) -> None:
        snapshots = [_snap(f"00000{i}") for i in range(1, 6)]
        uc = _make_uc(snapshots)
        result = uc.execute(SelectionCriteria(), as_of=AS_OF)
        assert result.total_screened == 5


class TestProviderIsPort:
    def test_use_case_does_not_depend_on_concrete_provider(self) -> None:
        # FakeMarketSnapshotProvider가 Protocol(런타임 체크 가능)에 부합하는지
        provider = FakeMarketSnapshotProvider()
        assert isinstance(provider, MarketSnapshotProvider)


class TestZeroNValues:
    def test_all_zero_returns_empty(self) -> None:
        snapshots = [_snap("000001", trading_value=5_000_000_000_000)]
        uc = _make_uc(snapshots)
        result = uc.execute(
            SelectionCriteria(top_volume_n=0, surge_top_n=0, plunge_top_n=0), as_of=AS_OF
        )
        assert result.candidates == ()
        assert result.total_screened == 1
