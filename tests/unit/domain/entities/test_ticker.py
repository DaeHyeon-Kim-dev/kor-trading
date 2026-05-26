"""Ticker 엔티티 테스트.

PRD: docs/PRD.md § 3.2 (Stock Selector 출력 스키마: ticker 6자리, market KOSPI/KOSDAQ)
DEVELOPMENT.md § 5.1 (Ticker 엔티티 예시)
"""

import dataclasses

import pytest

from kor_trading.domain.entities.ticker import Market, Ticker


class TestTickerConstruction:
    def test_accepts_valid_kospi(self) -> None:
        t = Ticker(code="005930", name="삼성전자", market="KOSPI")
        assert t.code == "005930"
        assert t.name == "삼성전자"
        assert t.market == "KOSPI"

    def test_accepts_valid_kosdaq(self) -> None:
        t = Ticker(code="035720", name="카카오", market="KOSDAQ")
        assert t.market == "KOSDAQ"


class TestTickerCodeValidation:
    def test_rejects_code_shorter_than_six(self) -> None:
        with pytest.raises(ValueError, match="ticker code"):
            Ticker(code="12345", name="X", market="KOSPI")

    def test_rejects_code_longer_than_six(self) -> None:
        with pytest.raises(ValueError, match="ticker code"):
            Ticker(code="1234567", name="X", market="KOSPI")

    def test_rejects_non_digit_code(self) -> None:
        with pytest.raises(ValueError, match="ticker code"):
            Ticker(code="00593A", name="X", market="KOSPI")

    def test_rejects_empty_code(self) -> None:
        with pytest.raises(ValueError, match="ticker code"):
            Ticker(code="", name="X", market="KOSPI")


class TestTickerNameValidation:
    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Ticker(code="005930", name="", market="KOSPI")

    def test_rejects_whitespace_only_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Ticker(code="005930", name="   ", market="KOSPI")


class TestTickerMarketValidation:
    def test_rejects_unknown_market(self) -> None:
        with pytest.raises(ValueError, match="market"):
            Ticker(code="005930", name="삼성전자", market="NASDAQ")  # type: ignore[arg-type]


class TestTickerEqualityAndImmutability:
    def test_equal_when_all_fields_equal(self) -> None:
        a = Ticker(code="005930", name="삼성전자", market="KOSPI")
        b = Ticker(code="005930", name="삼성전자", market="KOSPI")
        assert a == b

    def test_not_equal_when_code_differs(self) -> None:
        a = Ticker(code="005930", name="삼성전자", market="KOSPI")
        b = Ticker(code="005935", name="삼성전자", market="KOSPI")
        assert a != b

    def test_is_frozen(self) -> None:
        t = Ticker(code="005930", name="삼성전자", market="KOSPI")
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.name = "변경"  # type: ignore[misc]


class TestMarketType:
    def test_market_literal_is_exported(self) -> None:
        # type alias가 import 가능해야 함 (타입 힌트에서 사용)
        valid: Market = "KOSPI"
        assert valid == "KOSPI"
