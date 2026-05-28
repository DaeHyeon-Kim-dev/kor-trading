"""Indicator 분석 유스케이스 입출력 DTO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
    from kor_trading.domain.entities.ticker import Ticker
    from kor_trading.domain.services.indicator_scorer import IndicatorScores


@dataclass(frozen=True, slots=True)
class IndicatorAnalysisItem:
    snapshot: IndicatorSnapshot
    scores: IndicatorScores


@dataclass(frozen=True, slots=True)
class IndicatorAnalysisError:
    ticker: Ticker
    reason: str


@dataclass(frozen=True, slots=True)
class IndicatorAnalysisResult:
    as_of: date
    items: tuple[IndicatorAnalysisItem, ...]
    errors: tuple[IndicatorAnalysisError, ...]
