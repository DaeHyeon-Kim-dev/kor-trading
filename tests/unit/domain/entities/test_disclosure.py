"""Disclosure 엔티티 테스트."""

from datetime import date

import pytest

from kor_trading.domain.entities.disclosure import Disclosure, DisclosureSource


class TestConstruction:
    def test_accepts_valid_inputs(self) -> None:
        d = Disclosure(
            ticker_code="005930",
            date=date(2026, 5, 21),
            title="1Q 영업이익 사상 최대",
            source=DisclosureSource.DART,
            source_url="https://opendart.fss.or.kr/...",
            report_type="주요사항보고",
        )
        assert d.title == "1Q 영업이익 사상 최대"
        assert d.source == DisclosureSource.DART

    def test_report_type_optional(self) -> None:
        Disclosure(
            ticker_code="005930",
            date=date(2026, 5, 21),
            title="title",
            source=DisclosureSource.NAVER,
            source_url="https://...",
        )


class TestValidation:
    def test_rejects_blank_title(self) -> None:
        with pytest.raises(ValueError, match="title"):
            Disclosure(
                ticker_code="005930",
                date=date(2026, 5, 21),
                title="   ",
                source=DisclosureSource.DART,
                source_url="https://...",
            )

    def test_rejects_invalid_ticker_code(self) -> None:
        with pytest.raises(ValueError, match="ticker_code"):
            Disclosure(
                ticker_code="ABC",
                date=date(2026, 5, 21),
                title="t",
                source=DisclosureSource.DART,
                source_url="https://...",
            )
