"""AnalyzeIndicatorsUseCase — 종목 리스트별 지표 분석."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from kor_trading.application.dto.indicator_analysis import (
    IndicatorAnalysisError,
    IndicatorAnalysisItem,
    IndicatorAnalysisResult,
)
from kor_trading.domain.services.indicator_calculator import calculate_indicators
from kor_trading.domain.services.indicator_scorer import compute_scores

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
    from kor_trading.domain.entities.ticker import Ticker
    from kor_trading.domain.ports.investor_flow_provider import (
        InvestorFlow,
        InvestorFlowProvider,
    )
    from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider


log = structlog.get_logger()

_DEFAULT_LOOKBACK_DAYS = 120
_DEFAULT_WORKERS = 4
_PER_TICKER_TIMEOUT_S = 30


@dataclass
class AnalyzeIndicatorsUseCase:
    ohlcv_provider: OhlcvProvider
    flow_provider: InvestorFlowProvider | None = None

    def execute(
        self,
        tickers: list[Ticker],
        as_of: date,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        max_workers: int = _DEFAULT_WORKERS,
    ) -> IndicatorAnalysisResult:
        if not tickers:
            return IndicatorAnalysisResult(as_of=as_of, items=(), errors=())

        flows = self._fetch_flows(tickers, as_of)

        items: list[IndicatorAnalysisItem] = []
        errors: list[IndicatorAnalysisError] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_ticker = {
                pool.submit(self._analyze_one, t, as_of, lookback_days, flows.get(t.code)): t
                for t in tickers
            }
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    item = future.result(timeout=_PER_TICKER_TIMEOUT_S)
                    items.append(item)
                except Exception as e:  # 한 종목 실패가 전체를 막지 않도록
                    log.error("indicator.analyze.failed", ticker=ticker.code, error=str(e))
                    errors.append(IndicatorAnalysisError(ticker=ticker, reason=repr(e)))

        order = {t.code: i for i, t in enumerate(tickers)}
        items.sort(key=lambda x: order.get(x.snapshot.ticker.code, len(order)))
        return IndicatorAnalysisResult(as_of=as_of, items=tuple(items), errors=tuple(errors))

    def _fetch_flows(self, tickers: list[Ticker], as_of: date) -> dict[str, InvestorFlow]:
        if self.flow_provider is None:
            return {}
        ticker_codes = [t.code for t in tickers]
        try:
            return self.flow_provider.get_flows(ticker_codes, as_of)
        except Exception as e:  # 한 어댑터 실패가 지표 분석 전체를 막지 않도록
            log.error("indicator.flow_fetch_failed", error=str(e))
            return {}

    def _analyze_one(
        self,
        ticker: Ticker,
        as_of: date,
        lookback_days: int,
        flow: InvestorFlow | None,
    ) -> IndicatorAnalysisItem:
        bars = self.ohlcv_provider.get_daily_bars(ticker.code, as_of, lookback_days)
        snapshot = calculate_indicators(ticker, bars)
        snapshot = _merge_flow(snapshot, flow)
        scores = compute_scores(snapshot)
        return IndicatorAnalysisItem(snapshot=snapshot, scores=scores)


def _merge_flow(snapshot: IndicatorSnapshot, flow: InvestorFlow | None) -> IndicatorSnapshot:
    if flow is None:
        return snapshot
    return replace(
        snapshot,
        foreign_net_buy_5d=flow.foreign_net_5d,
        foreign_net_buy_20d=flow.foreign_net_20d,
        institution_net_buy_5d=flow.institution_net_5d,
        institution_net_buy_20d=flow.institution_net_20d,
    )
