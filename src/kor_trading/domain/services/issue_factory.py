"""Disclosure + LLM 분류 결과 → Issue 변환.

LLM 호출(sentiment/impact/summary 산출)은 어댑터의 책임이고,
이 함수는 그 결과와 시점 가중치를 결합해 Issue를 생산.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.entities.issue import Impact, Issue, Sentiment, impact_score
from kor_trading.domain.services.recency_decay import RecencyDecaySchedule, days_between

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.disclosure import Disclosure


_DEFAULT_SCHEDULE = RecencyDecaySchedule()


def build_issue(
    disclosure: Disclosure,
    *,
    as_of: date,
    sentiment: Sentiment,
    impact: Impact,
    confidence: float,
    summary: str,
    price_action_since: float | None = None,
    decay_schedule: RecencyDecaySchedule = _DEFAULT_SCHEDULE,
) -> Issue:
    recency = days_between(disclosure.date, as_of)
    decay = decay_schedule.weight_for(recency)
    effective = impact_score(impact) * decay
    return Issue(
        ticker_code=disclosure.ticker_code,
        date=disclosure.date,
        title=disclosure.title,
        source=disclosure.source,
        source_url=disclosure.source_url,
        sentiment=sentiment,
        impact=impact,
        confidence=confidence,
        summary=summary,
        recency_days=recency,
        decay_weight=decay,
        effective_impact=effective,
        price_action_since=price_action_since,
        report_type=disclosure.report_type,
    )
