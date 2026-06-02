"""AnalyzeIndicatorsUseCase 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from kor_trading.application.use_cases.analyze_indicators import AnalyzeIndicatorsUseCase
from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.ports.investor_flow_provider import InvestorFlow
from tests.fakes.fake_investor_flow_provider import FakeInvestorFlowProvider
from tests.fakes.fake_ohlcv_provider import FakeOhlcvProvider

AS_OF = date(2026, 5, 26)


def _t(code: str = "005930", name: str = "X") -> Ticker:
    return Ticker(code=code, name=name, market="KOSPI")


def _bars(closes: list[int]) -> list[OhlcvBar]:
    """bars의 마지막 일자가 AS_OF 이전이 되도록 충분히 이른 일자부터 생성."""
    bars: list[OhlcvBar] = []
    # 200 영업일 거슬러 = ~10개월 전부터 — len(closes)가 200 이내면 안전
    d = date(2025, 9, 1)
    for close in closes:
        while d.isoweekday() > 5:
            d += timedelta(days=1)
        bars.append(
            OhlcvBar(
                date=d,
                open=close,
                high=close + 100,
                low=max(0, close - 100),
                close=close,
                volume=1000,
                trading_value=close * 1000,
            )
        )
        d += timedelta(days=1)
    return bars


class TestEmptyTickers:
    def test_empty_tickers_returns_empty_result(self) -> None:
        provider = FakeOhlcvProvider()
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=provider)
        result = uc.execute([], AS_OF)
        assert result.items == ()
        assert result.errors == ()
        assert result.as_of == AS_OF


class TestSingleTicker:
    def test_analyzes_one_ticker(self) -> None:
        provider = FakeOhlcvProvider()
        provider.add_bars("005930", _bars([100 + i for i in range(130)]))
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=provider)

        result = uc.execute([_t()], AS_OF)
        assert len(result.items) == 1
        assert result.errors == ()
        item = result.items[0]
        assert item.snapshot.ticker.code == "005930"
        assert item.snapshot.sma_120 is not None
        assert item.snapshot.sma_alignment == "bullish"


class TestMultipleTickersOrder:
    def test_results_preserve_input_order(self) -> None:
        provider = FakeOhlcvProvider()
        for code in ("000001", "000002", "000003"):
            provider.add_bars(code, _bars([100 + i for i in range(30)]))
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=provider)

        result = uc.execute([_t("000001"), _t("000002"), _t("000003")], AS_OF, max_workers=2)
        codes = [item.snapshot.ticker.code for item in result.items]
        assert codes == ["000001", "000002", "000003"]


class TestPartialFailure:
    def test_one_failure_does_not_block_others(self) -> None:
        provider = FakeOhlcvProvider()
        provider.add_bars("000001", _bars([100] * 30))
        provider.add_bars("000003", _bars([100] * 30))
        provider.raise_for_ticker("000002")
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=provider)

        result = uc.execute([_t("000001"), _t("000002"), _t("000003")], AS_OF)
        assert len(result.items) == 2
        assert len(result.errors) == 1
        assert result.errors[0].ticker.code == "000002"


class TestInsufficientData:
    def test_short_history_yields_partial_indicators(self) -> None:
        provider = FakeOhlcvProvider()
        provider.add_bars("005930", _bars([100] * 5))  # 5일 — RSI/MACD 부족
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=provider)

        result = uc.execute([_t()], AS_OF)
        assert len(result.items) == 1
        snap = result.items[0].snapshot
        assert snap.sma_5 == 100.0
        assert snap.sma_20 is None
        assert snap.rsi_14 is None


class TestScoresIncluded:
    def test_scores_computed_for_each_item(self) -> None:
        provider = FakeOhlcvProvider()
        provider.add_bars("005930", _bars([100 + i for i in range(130)]))
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=provider)

        result = uc.execute([_t()], AS_OF)
        scores = result.items[0].scores
        assert scores.overall.value > 0
        assert "trend" in scores.category
        assert "ultra_short" in scores.by_horizon


class TestFlowIntegration:
    def test_flow_provider_fills_foreign_institution_fields(self) -> None:
        ohlcv = FakeOhlcvProvider()
        ohlcv.add_bars("005930", _bars([100 + i for i in range(130)]))
        flow = FakeInvestorFlowProvider()
        flow.set_flow(
            "005930",
            InvestorFlow(
                foreign_net_5d=12_500_000_000,
                foreign_net_20d=51_000_000_000,
                institution_net_5d=-3_200_000_000,
                institution_net_20d=8_400_000_000,
            ),
        )
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=ohlcv, flow_provider=flow)

        result = uc.execute([_t()], AS_OF)
        snap = result.items[0].snapshot
        assert snap.foreign_net_buy_5d == 12_500_000_000
        assert snap.foreign_net_buy_20d == 51_000_000_000
        assert snap.institution_net_buy_5d == -3_200_000_000
        # flow가 채워졌으니 flow 카테고리 점수가 0이 아니어야 함
        assert result.items[0].scores.category["flow"].value > 0

    def test_no_flow_provider_keeps_fields_none(self) -> None:
        ohlcv = FakeOhlcvProvider()
        ohlcv.add_bars("005930", _bars([100] * 30))
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=ohlcv)  # flow_provider=None
        result = uc.execute([_t()], AS_OF)
        snap = result.items[0].snapshot
        assert snap.foreign_net_buy_5d is None
        assert snap.institution_net_buy_5d is None

    def test_flow_provider_failure_does_not_block_analysis(self) -> None:
        ohlcv = FakeOhlcvProvider()
        ohlcv.add_bars("005930", _bars([100] * 30))
        flow = FakeInvestorFlowProvider()
        flow.configure_failure(on=True)
        uc = AnalyzeIndicatorsUseCase(ohlcv_provider=ohlcv, flow_provider=flow)
        result = uc.execute([_t()], AS_OF)
        # 지표는 그대로 산출, flow 필드는 None
        assert len(result.items) == 1
        assert result.items[0].snapshot.foreign_net_buy_5d is None
