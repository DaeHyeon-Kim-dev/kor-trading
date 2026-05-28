"""IndicatorSnapshot 엔티티 테스트.

종목 1개의 특정 시점 지표 계산 결과를 평탄한 dataclass로 보관.
nullable 필드 多 — 데이터 부족(상장 후 짧은 종목) 대응.

PRD: docs/PRD.md § 3.3 / docs/INDICATORS.md § 1~5, § 9
"""

import dataclasses
from datetime import date

import pytest

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.ticker import Ticker


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _minimal() -> dict[str, object]:
    return {"ticker": _t(), "as_of": date(2026, 5, 26)}


class TestConstruction:
    def test_all_nullable_allowed(self) -> None:
        snap = IndicatorSnapshot(**_minimal())  # type: ignore[arg-type]
        assert snap.ticker.code == "005930"
        assert snap.sma_5 is None
        assert snap.rsi_14 is None

    def test_accepts_full_set(self) -> None:
        snap = IndicatorSnapshot(
            **_minimal(),  # type: ignore[arg-type]
            sma_5=77800,
            sma_20=75200,
            sma_60=72100,
            sma_120=70500,
            sma_alignment="bullish",
            macd=1.2,
            macd_signal=0.8,
            macd_hist=0.4,
            macd_cross="golden_recent",
            macd_position="above_zero",
            rsi_14=62.3,
            bb_upper=80100,
            bb_mid=75200,
            bb_lower=70300,
            bb_position="upper_half",
            bb_squeeze=False,
            atr_14=1850,
            obv_trend="up",
            vwap_position="above",
            foreign_net_buy_5d=12_500_000_000,
            foreign_net_buy_20d=51_000_000_000,
            institution_net_buy_5d=-3_200_000_000,
            institution_net_buy_20d=8_400_000_000,
            short_balance_ratio=1.8,
        )
        assert snap.sma_alignment == "bullish"
        assert snap.macd_cross == "golden_recent"
        assert snap.rsi_14 == 62.3


class TestValidation:
    def test_rsi_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="rsi_14"):
            IndicatorSnapshot(**_minimal(), rsi_14=100.1)  # type: ignore[arg-type]

    def test_rsi_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="rsi_14"):
            IndicatorSnapshot(**_minimal(), rsi_14=-0.1)  # type: ignore[arg-type]

    def test_rsi_at_bounds_allowed(self) -> None:
        IndicatorSnapshot(**_minimal(), rsi_14=0.0)  # type: ignore[arg-type]
        IndicatorSnapshot(**_minimal(), rsi_14=100.0)  # type: ignore[arg-type]

    def test_bb_upper_below_lower_raises(self) -> None:
        with pytest.raises(ValueError, match="bb"):
            IndicatorSnapshot(
                **_minimal(),  # type: ignore[arg-type]
                bb_upper=70000,
                bb_mid=75000,
                bb_lower=80100,
            )

    def test_short_balance_ratio_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="short_balance_ratio"):
            IndicatorSnapshot(**_minimal(), short_balance_ratio=-1.0)  # type: ignore[arg-type]


class TestImmutability:
    def test_is_frozen(self) -> None:
        snap = IndicatorSnapshot(**_minimal(), rsi_14=50.0)  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.rsi_14 = 60.0  # type: ignore[misc]
