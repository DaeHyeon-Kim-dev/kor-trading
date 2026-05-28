"""Issue 엔티티 테스트."""

from datetime import date

import pytest

from kor_trading.domain.entities.disclosure import DisclosureSource
from kor_trading.domain.entities.issue import Impact, Issue, Sentiment, impact_score


def _valid_kwargs() -> dict[str, object]:
    return {
        "ticker_code": "005930",
        "date": date(2026, 5, 21),
        "title": "1Q 영업이익 사상 최대",
        "source": DisclosureSource.DART,
        "source_url": "https://...",
        "sentiment": Sentiment.POSITIVE,
        "impact": Impact.HIGH,
        "confidence": 0.95,
        "summary": "AI 반도체 수요로 어닝 서프라이즈",
        "recency_days": 5,
        "decay_weight": 0.60,
        "effective_impact": 0.60,
        "price_action_since": 4.8,
        "report_type": "주요사항보고",
    }


class TestConstruction:
    def test_accepts_valid(self) -> None:
        issue = Issue(**_valid_kwargs())  # type: ignore[arg-type]
        assert issue.sentiment == Sentiment.POSITIVE
        assert issue.impact == Impact.HIGH

    def test_price_action_optional(self) -> None:
        kw = _valid_kwargs() | {"price_action_since": None}
        Issue(**kw)  # type: ignore[arg-type]


class TestValidation:
    def test_rejects_confidence_above_one(self) -> None:
        kw = _valid_kwargs() | {"confidence": 1.1}
        with pytest.raises(ValueError, match="confidence"):
            Issue(**kw)  # type: ignore[arg-type]

    def test_rejects_decay_weight_negative(self) -> None:
        kw = _valid_kwargs() | {"decay_weight": -0.1}
        with pytest.raises(ValueError, match="decay_weight"):
            Issue(**kw)  # type: ignore[arg-type]

    def test_rejects_effective_impact_above_one(self) -> None:
        kw = _valid_kwargs() | {"effective_impact": 1.5}
        with pytest.raises(ValueError, match="effective_impact"):
            Issue(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_recency(self) -> None:
        kw = _valid_kwargs() | {"recency_days": -1}
        with pytest.raises(ValueError, match="recency_days"):
            Issue(**kw)  # type: ignore[arg-type]

    def test_rejects_blank_title(self) -> None:
        kw = _valid_kwargs() | {"title": ""}
        with pytest.raises(ValueError, match="title"):
            Issue(**kw)  # type: ignore[arg-type]


class TestImpactScore:
    def test_high_is_one(self) -> None:
        assert impact_score(Impact.HIGH) == 1.0

    def test_medium_is_06(self) -> None:
        assert impact_score(Impact.MEDIUM) == 0.6

    def test_low_is_03(self) -> None:
        assert impact_score(Impact.LOW) == 0.3
