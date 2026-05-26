"""OhlcvBar 엔티티 테스트.

PRD: docs/PRD.md § 3.2 (Stock Selector — close, volume, trading_value 사용)
docs/INDICATORS.md § 1~4 (지표 계산용 일봉 시계열)
"""

import dataclasses
from datetime import date

import pytest

from kor_trading.domain.entities.ohlcv_bar import OhlcvBar


def _valid_kwargs() -> dict[str, object]:
    return {
        "date": date(2026, 5, 26),
        "open": 78000,
        "high": 79000,
        "low": 77500,
        "close": 78500,
        "volume": 25_300_000,
        "trading_value": 1_980_000_000_000,
    }


class TestOhlcvBarConstruction:
    def test_accepts_valid_inputs(self) -> None:
        bar = OhlcvBar(**_valid_kwargs())  # type: ignore[arg-type]
        assert bar.close == 78500
        assert bar.trading_value == 1_980_000_000_000

    def test_close_can_equal_open(self) -> None:
        kw = _valid_kwargs() | {"open": 78000, "close": 78000}
        OhlcvBar(**kw)  # type: ignore[arg-type]


class TestOhlcvBarPriceValidation:
    def test_rejects_high_below_low(self) -> None:
        kw = _valid_kwargs() | {"high": 77000, "low": 77500}
        with pytest.raises(ValueError, match="high"):
            OhlcvBar(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_open(self) -> None:
        kw = _valid_kwargs() | {"open": -1}
        with pytest.raises(ValueError, match="non-negative"):
            OhlcvBar(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_close(self) -> None:
        kw = _valid_kwargs() | {"close": -1}
        with pytest.raises(ValueError, match="non-negative"):
            OhlcvBar(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_high(self) -> None:
        kw = _valid_kwargs() | {"high": -1, "low": -10}
        with pytest.raises(ValueError, match="non-negative"):
            OhlcvBar(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_low(self) -> None:
        kw = _valid_kwargs() | {"low": -1}
        with pytest.raises(ValueError, match="non-negative"):
            OhlcvBar(**kw)  # type: ignore[arg-type]


class TestOhlcvBarVolumeValidation:
    def test_rejects_negative_volume(self) -> None:
        kw = _valid_kwargs() | {"volume": -1}
        with pytest.raises(ValueError, match="non-negative"):
            OhlcvBar(**kw)  # type: ignore[arg-type]

    def test_rejects_negative_trading_value(self) -> None:
        kw = _valid_kwargs() | {"trading_value": -1}
        with pytest.raises(ValueError, match="non-negative"):
            OhlcvBar(**kw)  # type: ignore[arg-type]

    def test_zero_volume_allowed(self) -> None:
        # 거래정지 등으로 거래량 0 가능
        kw = _valid_kwargs() | {"volume": 0, "trading_value": 0}
        OhlcvBar(**kw)  # type: ignore[arg-type]


class TestOhlcvBarImmutability:
    def test_is_frozen(self) -> None:
        bar = OhlcvBar(**_valid_kwargs())  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            bar.close = 80000  # type: ignore[misc]

    def test_equal_when_all_fields_equal(self) -> None:
        a = OhlcvBar(**_valid_kwargs())  # type: ignore[arg-type]
        b = OhlcvBar(**_valid_kwargs())  # type: ignore[arg-type]
        assert a == b
