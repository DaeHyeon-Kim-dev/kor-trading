"""PykrxInvestorFlowProvider 단위 테스트 (fake pykrx 모듈)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from kor_trading.adapters.outbound.pykrx_investor_flow import PykrxInvestorFlowProvider
from kor_trading.domain.ports.investor_flow_provider import InvestorFlowProvider

AS_OF = date(2026, 5, 26)


class _FakePykrxFlow:
    def __init__(
        self,
        responses: dict[tuple[str, str], pd.DataFrame] | None = None,
        raise_for: tuple[str, str] | None = None,
    ) -> None:
        # key: (market, investor) → DataFrame
        self._responses = responses or {}
        self._raise_for = raise_for
        self.calls: list[tuple[str, str, str, str]] = []

    def get_market_net_purchases_of_equities(
        self, start_date: str, end_date: str, market: str, investor: str
    ) -> Any:
        self.calls.append((start_date, end_date, market, investor))
        if (market, investor) == self._raise_for:
            raise RuntimeError("network down")
        return self._responses.get((market, investor), pd.DataFrame())


def _flow_df(rows: list[tuple[str, int]]) -> pd.DataFrame:
    """rows: (ticker, 순매수거래대금)."""
    return pd.DataFrame(
        {"순매수거래대금": [r[1] for r in rows]},
        index=[r[0] for r in rows],
    )


class TestNormalFetch:
    def test_returns_flow_for_ticker(self) -> None:
        fake = _FakePykrxFlow(
            responses={
                ("KOSPI", "외국인"): _flow_df([("005930", 12_500_000_000)]),
                ("KOSPI", "기관합계"): _flow_df([("005930", -3_200_000_000)]),
            }
        )
        provider = PykrxInvestorFlowProvider(stock_module=fake)
        flows = provider.get_flows(("KOSPI",), AS_OF)
        # 5d=20d 같은 데이터 반환 (responses 키가 (market, investor)이라 5d/20d 구분 없음)
        # 실제로는 둘 다 들어옴
        assert "005930" in flows
        assert flows["005930"].foreign_net_5d == 12_500_000_000
        assert flows["005930"].institution_net_5d == -3_200_000_000

    def test_calls_4_apis_per_market(self) -> None:
        fake = _FakePykrxFlow()
        provider = PykrxInvestorFlowProvider(stock_module=fake)
        provider.get_flows(("KOSPI", "KOSDAQ"), AS_OF)
        # 2 markets * 2 investors * 2 lookbacks = 8 calls
        assert len(fake.calls) == 8


class TestFailureIsolation:
    def test_single_call_failure_yields_partial_result(self) -> None:
        fake = _FakePykrxFlow(
            responses={
                ("KOSPI", "외국인"): _flow_df([("005930", 100)]),
                # ("KOSPI", "기관합계") 호출은 예외
            },
            raise_for=("KOSPI", "기관합계"),
        )
        provider = PykrxInvestorFlowProvider(stock_module=fake)
        flows = provider.get_flows(("KOSPI",), AS_OF)
        assert "005930" in flows
        # foreign는 채워졌고, institution은 None
        assert flows["005930"].foreign_net_5d == 100
        assert flows["005930"].institution_net_5d is None


class TestSkipInvalidRows:
    def test_skips_row_with_non_int_value(self) -> None:
        fake = _FakePykrxFlow(
            responses={
                ("KOSPI", "외국인"): pd.DataFrame(
                    {"순매수거래대금": ["bad", 100]},
                    index=["000001", "000002"],
                ),
            }
        )
        provider = PykrxInvestorFlowProvider(stock_module=fake)
        flows = provider.get_flows(("KOSPI",), AS_OF)
        assert flows["000001"].foreign_net_5d is None  # 변환 실패 skip
        assert flows["000002"].foreign_net_5d == 100


class TestZeroPaddedCodes:
    def test_pads_short_codes(self) -> None:
        fake = _FakePykrxFlow(
            responses={
                ("KOSPI", "외국인"): _flow_df([("5930", 100)]),
            }
        )
        provider = PykrxInvestorFlowProvider(stock_module=fake)
        flows = provider.get_flows(("KOSPI",), AS_OF)
        assert "005930" in flows


class TestProtocolConformance:
    def test_implements_investor_flow_provider(self) -> None:
        provider = PykrxInvestorFlowProvider(stock_module=_FakePykrxFlow())
        assert isinstance(provider, InvestorFlowProvider)
