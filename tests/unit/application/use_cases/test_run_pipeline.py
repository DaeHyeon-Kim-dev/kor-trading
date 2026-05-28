"""RunPipelineUseCase 통합 흐름 테스트 (fake adapter 사용)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from kor_trading.adapters.outbound.filesystem_report_repository import (
    FileSystemReportRepository,
)
from kor_trading.application.dto.selection import SelectionCriteria
from kor_trading.application.use_cases.analyze_indicators import AnalyzeIndicatorsUseCase
from kor_trading.application.use_cases.generate_report import GenerateReportUseCase
from kor_trading.application.use_cases.run_pipeline import RunPipelineUseCase
from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase
from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Ticker
from tests.fakes.fake_market_snapshot_provider import FakeMarketSnapshotProvider
from tests.fakes.fake_ohlcv_provider import FakeOhlcvProvider

if TYPE_CHECKING:
    from pathlib import Path


AS_OF = date(2026, 5, 26)


class _StubNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.documents: list[tuple[str, bytes]] = []

    def send_message(self, text: str) -> None:
        self.messages.append(text)

    def send_document(self, filename: str, content: bytes, caption: str | None = None) -> None:
        _ = caption
        self.documents.append((filename, content))


def _build_pipeline(
    snapshots: list[StockSnapshot], bars_by_ticker: dict[str, list[OhlcvBar]], tmp_path: Path
) -> tuple[RunPipelineUseCase, _StubNotifier]:
    market = FakeMarketSnapshotProvider()
    market.add_many(snapshots)
    ohlcv = FakeOhlcvProvider()
    for code, bars in bars_by_ticker.items():
        ohlcv.add_bars(code, bars)
    notifier = _StubNotifier()
    repo = FileSystemReportRepository(base_path=tmp_path)

    pipeline = RunPipelineUseCase(
        select_stocks=SelectStocksUseCase(market_snapshots=market),
        analyze_indicators=AnalyzeIndicatorsUseCase(ohlcv_provider=ohlcv),
        generate_report=GenerateReportUseCase(repository=repo, notifier=notifier),
    )
    return pipeline, notifier


def _stock_snap(code: str, *, trading_value: int = 1_000_000_000) -> StockSnapshot:
    return StockSnapshot(
        ticker=Ticker(code=code, name=code, market="KOSPI"),
        as_of=AS_OF,
        close=10_000,
        change_pct=2.0,
        volume=100_000,
        trading_value=trading_value,
        market_cap=1_000_000_000_000,
    )


def _bars(closes: list[int]) -> list[OhlcvBar]:
    bars: list[OhlcvBar] = []
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


class TestRunPipelineEndToEnd:
    def test_runs_selection_to_report(self, tmp_path: Path) -> None:
        snapshots = [
            _stock_snap("005930", trading_value=5_000_000_000_000),
            _stock_snap("035720", trading_value=2_000_000_000_000),
        ]
        bars_by_ticker = {
            "005930": _bars([100 + i for i in range(130)]),
            "035720": _bars([200 - i for i in range(130)]),
        }
        pipeline, notifier = _build_pipeline(snapshots, bars_by_ticker, tmp_path)

        report = pipeline.execute(
            criteria=SelectionCriteria(top_volume_n=5, surge_top_n=0, plunge_top_n=0),
            as_of=AS_OF,
            run_id="2026-05-26/1430",
        )

        # 1) 리포트 마크다운이 저장됨
        assert report.report_path.exists()
        content = report.report_path.read_text(encoding="utf-8")
        assert "005930" in content
        assert "035720" in content

        # 2) 종목별 evidence 저장
        assert len(report.evidence_paths) == 2

        # 3) 텔레그램 전송 시도
        assert len(notifier.messages) == 1
        assert len(notifier.documents) == 1

    def test_empty_selection_still_produces_report(self, tmp_path: Path) -> None:
        # 시총 미달 → 후보 0
        snap = _stock_snap("005930")
        pipeline, _ = _build_pipeline([snap], {}, tmp_path)
        report = pipeline.execute(
            criteria=SelectionCriteria(
                top_volume_n=5,
                surge_top_n=0,
                plunge_top_n=0,
                market_cap_min_krw=10_000_000_000_000_000,
            ),
            as_of=AS_OF,
            run_id="r1",
        )
        assert report.report_path.exists()
