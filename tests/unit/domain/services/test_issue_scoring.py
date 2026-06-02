"""aggregate_issue_score 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from kor_trading.domain.entities.disclosure import DisclosureSource
from kor_trading.domain.entities.issue import Impact, Issue, Sentiment
from kor_trading.domain.services.issue_scoring import aggregate_issue_score


def _issue(
    sentiment: Sentiment,
    *,
    effective_impact: float = 1.0,
    confidence: float = 1.0,
) -> Issue:
    return Issue(
        ticker_code="005930",
        date=date(2026, 5, 26),
        title="t",
        source=DisclosureSource.DART,
        source_url="https://...",
        sentiment=sentiment,
        impact=Impact.HIGH,
        confidence=confidence,
        summary="s",
        recency_days=0,
        decay_weight=1.0,
        effective_impact=effective_impact,
    )


class TestAggregate:
    def test_empty_is_zero(self) -> None:
        assert aggregate_issue_score([]) == 0.0

    def test_single_positive_full(self) -> None:
        assert aggregate_issue_score([_issue(Sentiment.POSITIVE)]) == 1.0

    def test_single_negative_full(self) -> None:
        assert aggregate_issue_score([_issue(Sentiment.NEGATIVE)]) == -1.0

    def test_neutral_contributes_zero(self) -> None:
        assert aggregate_issue_score([_issue(Sentiment.NEUTRAL)]) == 0.0

    def test_decay_and_confidence_scale(self) -> None:
        score = aggregate_issue_score(
            [_issue(Sentiment.POSITIVE, effective_impact=0.6, confidence=0.5)]
        )
        assert score == pytest.approx(0.3)

    def test_multiple_positive_accumulate_and_clip(self) -> None:
        issues = [_issue(Sentiment.POSITIVE) for _ in range(3)]
        assert aggregate_issue_score(issues) == 1.0  # 3.0 → clip 1.0

    def test_mixed_offsets(self) -> None:
        issues = [
            _issue(Sentiment.POSITIVE, effective_impact=0.5, confidence=1.0),
            _issue(Sentiment.NEGATIVE, effective_impact=0.5, confidence=1.0),
        ]
        assert aggregate_issue_score(issues) == pytest.approx(0.0)
