"""AnalyzeIssuesUseCase — 종목별 공시 fetch → LLM 분류 → Issue + 점수."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from kor_trading.application.dto.issue_analysis import (
    IssueAnalysisItem,
    IssueAnalysisResult,
)
from kor_trading.domain.services.disclosure_filter import is_noise_disclosure
from kor_trading.domain.services.issue_factory import build_issue
from kor_trading.domain.services.issue_scoring import aggregate_issue_score

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.disclosure import Disclosure
    from kor_trading.domain.entities.issue import Issue
    from kor_trading.domain.entities.ticker import Ticker
    from kor_trading.domain.ports.disclosure_provider import DisclosureProvider
    from kor_trading.domain.ports.sentiment_classifier import SentimentClassifier


log = structlog.get_logger()

_DEFAULT_LOOKBACK_DAYS = 7
_DEFAULT_WORKERS = 4
_PER_TICKER_TIMEOUT_S = 120
_MAX_ISSUES_PER_TICKER = 20


@dataclass
class AnalyzeIssuesUseCase:
    disclosure_provider: DisclosureProvider
    classifier: SentimentClassifier

    def execute(
        self,
        tickers: list[Ticker],
        as_of: date,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        max_workers: int = _DEFAULT_WORKERS,
        max_issues_per_ticker: int = _MAX_ISSUES_PER_TICKER,
    ) -> IssueAnalysisResult:
        if not tickers:
            return IssueAnalysisResult(as_of=as_of, items=())

        items: list[IssueAnalysisItem] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._analyze_one, t, as_of, lookback_days, max_issues_per_ticker): t
                for t in tickers
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    item = future.result(timeout=_PER_TICKER_TIMEOUT_S)
                    if item is not None:
                        items.append(item)
                except Exception as e:  # 한 종목 실패가 전체를 막지 않도록
                    log.error("issue.analyze.failed", ticker=ticker.code, error=str(e))

        order = {t.code: i for i, t in enumerate(tickers)}
        items.sort(key=lambda x: order.get(x.ticker_code, len(order)))
        return IssueAnalysisResult(as_of=as_of, items=tuple(items))

    def _analyze_one(
        self, ticker: Ticker, as_of: date, lookback_days: int, max_issues: int
    ) -> IssueAnalysisItem | None:
        disclosures = self.disclosure_provider.get_recent(ticker.code, as_of, lookback_days)
        # 노이즈 공시(임원 소유상황·기업집단현황 등)는 분류 전 제외
        material = [d for d in disclosures if not is_noise_disclosure(d.title)]
        if not material:
            return None

        issues: list[Issue] = []
        for disclosure in material[:max_issues]:
            issue = self._to_issue(disclosure, as_of)
            if issue is not None:
                issues.append(issue)

        if not issues:
            return None

        return IssueAnalysisItem(
            ticker_code=ticker.code,
            issues=tuple(issues),
            overall_score=aggregate_issue_score(issues),
        )

    def _to_issue(self, disclosure: Disclosure, as_of: date) -> Issue | None:
        classification = self.classifier.classify(disclosure.title, context=disclosure.report_type)
        if classification is None:
            return None
        return build_issue(
            disclosure,
            as_of=as_of,
            sentiment=classification.sentiment,
            impact=classification.impact,
            confidence=classification.confidence,
            summary=classification.summary,
        )
