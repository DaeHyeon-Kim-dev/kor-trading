"""AnalyzeIndicatorsUseCase — 종목 리스트별 지표 분석."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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

    from kor_trading.domain.entities.ticker import Ticker
    from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider


log = structlog.get_logger()

_DEFAULT_LOOKBACK_DAYS = 120
_DEFAULT_WORKERS = 4
_PER_TICKER_TIMEOUT_S = 30


@dataclass
class AnalyzeIndicatorsUseCase:
    ohlcv_provider: OhlcvProvider

    def execute(
        self,
        tickers: list[Ticker],
        as_of: date,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        max_workers: int = _DEFAULT_WORKERS,
    ) -> IndicatorAnalysisResult:
        if not tickers:
            return IndicatorAnalysisResult(as_of=as_of, items=(), errors=())

        items: list[IndicatorAnalysisItem] = []
        errors: list[IndicatorAnalysisError] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_ticker = {
                pool.submit(self._analyze_one, t, as_of, lookback_days): t for t in tickers
            }
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    item = future.result(timeout=_PER_TICKER_TIMEOUT_S)
                    items.append(item)
                except Exception as e:  # 한 종목 실패가 전체를 막지 않도록
                    log.error("indicator.analyze.failed", ticker=ticker.code, error=str(e))
                    errors.append(IndicatorAnalysisError(ticker=ticker, reason=repr(e)))

        # 입력 순서 보존
        order = {t.code: i for i, t in enumerate(tickers)}
        items.sort(key=lambda x: order.get(x.snapshot.ticker.code, len(order)))
        return IndicatorAnalysisResult(as_of=as_of, items=tuple(items), errors=tuple(errors))

    def _analyze_one(
        self, ticker: Ticker, as_of: date, lookback_days: int
    ) -> IndicatorAnalysisItem:
        bars = self.ohlcv_provider.get_daily_bars(ticker.code, as_of, lookback_days)
        snapshot = calculate_indicators(ticker, bars)
        scores = compute_scores(snapshot)
        return IndicatorAnalysisItem(snapshot=snapshot, scores=scores)
