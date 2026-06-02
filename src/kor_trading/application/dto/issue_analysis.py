"""Issue 분석 유스케이스 출력 DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.issue import Issue


@dataclass(frozen=True, slots=True)
class IssueAnalysisItem:
    ticker_code: str
    issues: tuple[Issue, ...]
    overall_score: float  # -1.0 ~ +1.0 (decay·sentiment 가중 합)


@dataclass(frozen=True, slots=True)
class IssueAnalysisResult:
    as_of: date
    items: tuple[IssueAnalysisItem, ...] = field(default_factory=tuple)

    def score_for(self, ticker_code: str) -> float:
        for item in self.items:
            if item.ticker_code == ticker_code:
                return item.overall_score
        return 0.0

    def issues_for(self, ticker_code: str) -> tuple[Issue, ...]:
        for item in self.items:
            if item.ticker_code == ticker_code:
                return item.issues
        return ()
