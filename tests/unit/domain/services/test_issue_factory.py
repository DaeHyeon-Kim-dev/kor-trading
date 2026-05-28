"""Disclosure → Issue 변환 테스트."""

from datetime import date

import pytest

from kor_trading.domain.entities.disclosure import Disclosure, DisclosureSource
from kor_trading.domain.entities.issue import Impact, Sentiment
from kor_trading.domain.services.issue_factory import build_issue


def _d(disclosure_date: date) -> Disclosure:
    return Disclosure(
        ticker_code="005930",
        date=disclosure_date,
        title="1Q 어닝 서프라이즈",
        source=DisclosureSource.DART,
        source_url="https://...",
        report_type="주요사항보고",
    )


class TestBuildIssue:
    def test_today_disclosure_full_impact(self) -> None:
        issue = build_issue(
            _d(date(2026, 5, 26)),
            as_of=date(2026, 5, 26),
            sentiment=Sentiment.POSITIVE,
            impact=Impact.HIGH,
            confidence=0.95,
            summary="AI 반도체 수요로 어닝",
        )
        assert issue.recency_days == 0
        assert issue.decay_weight == 1.0
        assert issue.effective_impact == 1.0

    def test_five_days_old_decayed(self) -> None:
        issue = build_issue(
            _d(date(2026, 5, 21)),
            as_of=date(2026, 5, 26),
            sentiment=Sentiment.POSITIVE,
            impact=Impact.HIGH,
            confidence=0.95,
            summary="...",
        )
        assert issue.recency_days == 5
        assert issue.decay_weight == 0.60
        assert issue.effective_impact == pytest.approx(0.60)  # 1.0 * 0.6

    def test_medium_impact_with_recent(self) -> None:
        issue = build_issue(
            _d(date(2026, 5, 25)),
            as_of=date(2026, 5, 26),
            sentiment=Sentiment.NEUTRAL,
            impact=Impact.MEDIUM,
            confidence=0.7,
            summary="...",
        )
        assert issue.effective_impact == pytest.approx(0.6 * 0.85)

    def test_inherits_disclosure_fields(self) -> None:
        issue = build_issue(
            _d(date(2026, 5, 26)),
            as_of=date(2026, 5, 26),
            sentiment=Sentiment.POSITIVE,
            impact=Impact.HIGH,
            confidence=0.95,
            summary="요약",
        )
        assert issue.ticker_code == "005930"
        assert issue.title == "1Q 어닝 서프라이즈"
        assert issue.source == DisclosureSource.DART
        assert issue.report_type == "주요사항보고"

    def test_price_action_since_passed_through(self) -> None:
        issue = build_issue(
            _d(date(2026, 5, 21)),
            as_of=date(2026, 5, 26),
            sentiment=Sentiment.POSITIVE,
            impact=Impact.HIGH,
            confidence=0.95,
            summary="...",
            price_action_since=4.8,
        )
        assert issue.price_action_since == 4.8
