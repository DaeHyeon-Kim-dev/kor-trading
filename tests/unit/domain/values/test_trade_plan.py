"""TradePlan / suggested_shares 테스트."""

from __future__ import annotations

import pytest

from kor_trading.domain.values.trade_plan import TradePlan, suggested_shares


def _plan(**kw: object) -> TradePlan:
    base: dict[str, object] = dict(
        setup="돌파",
        quality=0.7,
        entry=10_000,
        stop=9_600,
        target1=11_000,
        target2=11_400,
        risk_per_share=400,
        reward_risk=2.5,
        stop_pct=-4.0,
        rationale="r",
        invalidation="i",
    )
    base.update(kw)
    return TradePlan(**base)  # type: ignore[arg-type]


class TestTradePlan:
    def test_valid(self) -> None:
        assert _plan().setup == "돌파"

    def test_quality_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="quality"):
            _plan(quality=1.2)

    def test_stop_not_below_entry(self) -> None:
        with pytest.raises(ValueError, match="stop"):
            _plan(stop=10_000, entry=10_000)


class TestSuggestedShares:
    def test_normal(self) -> None:
        # 1,000만원 계좌, 1% 리스크(10만원) ÷ 400원 = 250주
        assert suggested_shares(10_000_000, 1.0, 400) == 250

    def test_floor(self) -> None:
        assert suggested_shares(10_000_000, 1.0, 333) == 300  # 100000//333

    def test_zero_risk_returns_zero(self) -> None:
        assert suggested_shares(10_000_000, 1.0, 0) == 0
