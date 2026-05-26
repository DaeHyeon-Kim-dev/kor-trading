"""Selection DTO (SelectionCriteria, SelectionCandidate, SelectionResult) 테스트.

PRD: docs/PRD.md § 3.2 — Stock Selector 입출력 명세
config/default.yaml § selection — 기본값 출처
"""

import dataclasses
from datetime import date

import pytest

from kor_trading.application.dto.selection import (
    SelectionCandidate,
    SelectionCriteria,
    SelectionResult,
)
from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Ticker


def _snap(code: str = "005930", trading_value: int = 1_000_000_000) -> StockSnapshot:
    return StockSnapshot(
        ticker=Ticker(code=code, name="X", market="KOSPI"),
        as_of=date(2026, 5, 26),
        close=78500,
        change_pct=5.2,
        volume=25_000_000,
        trading_value=trading_value,
        market_cap=469_000_000_000_000,
    )


# ──────────────────── SelectionCriteria ────────────────────
class TestSelectionCriteriaDefaults:
    def test_defaults_match_config(self) -> None:
        c = SelectionCriteria()
        assert c.top_volume_n == 50
        assert c.surge_top_n == 10
        assert c.plunge_top_n == 10
        assert c.market_cap_min_krw == 50_000_000_000
        assert c.max_candidates == 30
        assert c.markets == ("KOSPI", "KOSDAQ")


class TestSelectionCriteriaValidation:
    def test_rejects_negative_top_volume_n(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            SelectionCriteria(top_volume_n=-1)

    def test_rejects_negative_surge_top_n(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            SelectionCriteria(surge_top_n=-1)

    def test_rejects_negative_plunge_top_n(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            SelectionCriteria(plunge_top_n=-1)

    def test_rejects_zero_max_candidates(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            SelectionCriteria(max_candidates=0)

    def test_rejects_empty_markets(self) -> None:
        with pytest.raises(ValueError, match="market"):
            SelectionCriteria(markets=())

    def test_zero_top_volume_n_allowed(self) -> None:
        # "급등만 보고 싶다" 시나리오
        SelectionCriteria(top_volume_n=0, surge_top_n=10)


# ──────────────────── SelectionCandidate ────────────────────
class TestSelectionCandidate:
    def test_accepts_valid_inputs(self) -> None:
        c = SelectionCandidate(
            snapshot=_snap(),
            selection_reasons=("top_volume",),
            rank_by_volume=1,
            rank_by_change_up=None,
            rank_by_change_down=None,
        )
        assert c.snapshot.ticker.code == "005930"
        assert c.selection_reasons == ("top_volume",)

    def test_multiple_selection_reasons(self) -> None:
        c = SelectionCandidate(
            snapshot=_snap(),
            selection_reasons=("top_volume", "surge"),
            rank_by_volume=3,
            rank_by_change_up=7,
            rank_by_change_down=None,
        )
        assert "top_volume" in c.selection_reasons
        assert "surge" in c.selection_reasons

    def test_rejects_empty_selection_reasons(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            SelectionCandidate(
                snapshot=_snap(),
                selection_reasons=(),
                rank_by_volume=None,
                rank_by_change_up=None,
                rank_by_change_down=None,
            )

    def test_rejects_unknown_selection_reason(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            SelectionCandidate(
                snapshot=_snap(),
                selection_reasons=("bogus",),
                rank_by_volume=None,
                rank_by_change_up=None,
                rank_by_change_down=None,
            )

    def test_is_frozen(self) -> None:
        c = SelectionCandidate(
            snapshot=_snap(),
            selection_reasons=("top_volume",),
            rank_by_volume=1,
            rank_by_change_up=None,
            rank_by_change_down=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.rank_by_volume = 2  # type: ignore[misc]


# ──────────────────── SelectionResult ────────────────────
class TestSelectionResult:
    def test_accepts_empty_candidates(self) -> None:
        r = SelectionResult(
            as_of=date(2026, 5, 26),
            total_screened=2350,
            candidates=(),
        )
        assert r.total_screened == 2350
        assert r.candidates == ()

    def test_rejects_negative_total_screened(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            SelectionResult(
                as_of=date(2026, 5, 26),
                total_screened=-1,
                candidates=(),
            )

    def test_is_frozen(self) -> None:
        r = SelectionResult(
            as_of=date(2026, 5, 26),
            total_screened=10,
            candidates=(),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.total_screened = 5  # type: ignore[misc]
