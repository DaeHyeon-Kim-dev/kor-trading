"""StockSnapshot 엔티티 테스트.

특정 시점 한 종목의 시장 스냅샷 (종가, 등락률, 거래량, 거래대금, 시총).
Stock Selector 유스케이스의 입력 단위.

PRD: docs/PRD.md § 3.2 (Stock Selector 출력에 close/change_pct/volume/trading_value/market_cap)
"""

import dataclasses
from datetime import date

import pytest

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Ticker


def _t() -> Ticker:
    return Ticker(code="005930", name="삼성전자", market="KOSPI")


def _valid_kwargs() -> dict[str, object]:
    return {
        "ticker": _t(),
        "as_of": date(2026, 5, 26),
        "close": 78500,
        "change_pct": 5.2,
        "volume": 25_300_000,
        "trading_value": 1_980_000_000_000,
        "market_cap": 469_000_000_000_000,
    }


class TestStockSnapshotConstruction:
    def test_accepts_valid_inputs(self) -> None:
        snap = StockSnapshot(**_valid_kwargs())  # type: ignore[arg-type]
        assert snap.ticker.code == "005930"
        assert snap.close == 78500
        assert snap.change_pct == 5.2

    def test_change_pct_can_be_negative(self) -> None:
        # 급락 종목은 음수
        kw = _valid_kwargs() | {"change_pct": -7.3}
        snap = StockSnapshot(**kw)  # type: ignore[arg-type]
        assert snap.change_pct == -7.3

    def test_change_pct_can_be_zero(self) -> None:
        kw = _valid_kwargs() | {"change_pct": 0.0}
        StockSnapshot(**kw)  # type: ignore[arg-type]


class TestStockSnapshotNonNegativeFields:
    def test_rejects_negative_close(self) -> None:
        kw = _valid_kwargs() | {"close": -1}
        with pytest.raises(ValueError, match="non-negative"):
            StockSnapshot(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_volume(self) -> None:
        kw = _valid_kwargs() | {"volume": -1}
        with pytest.raises(ValueError, match="non-negative"):
            StockSnapshot(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_trading_value(self) -> None:
        kw = _valid_kwargs() | {"trading_value": -1}
        with pytest.raises(ValueError, match="non-negative"):
            StockSnapshot(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_market_cap(self) -> None:
        kw = _valid_kwargs() | {"market_cap": -1}
        with pytest.raises(ValueError, match="non-negative"):
            StockSnapshot(**kw)  # type: ignore[arg-type]

    def test_zero_values_allowed(self) -> None:
        # 거래정지: volume=0, trading_value=0 가능
        kw = _valid_kwargs() | {"volume": 0, "trading_value": 0}
        StockSnapshot(**kw)  # type: ignore[arg-type]


class TestStockSnapshotImmutability:
    def test_is_frozen(self) -> None:
        snap = StockSnapshot(**_valid_kwargs())  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.close = 80000  # type: ignore[misc]

    def test_equal_when_all_fields_equal(self) -> None:
        a = StockSnapshot(**_valid_kwargs())  # type: ignore[arg-type]
        b = StockSnapshot(**_valid_kwargs())  # type: ignore[arg-type]
        assert a == b
