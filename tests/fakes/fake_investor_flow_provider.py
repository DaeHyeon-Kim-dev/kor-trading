"""in-memory FakeInvestorFlowProvider — 단위 테스트용."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from kor_trading.domain.ports.investor_flow_provider import InvestorFlow


class FakeInvestorFlowProvider:
    def __init__(self) -> None:
        self._flows: dict[str, InvestorFlow] = {}
        self._raise = False

    def set_flow(self, ticker_code: str, flow: InvestorFlow) -> None:
        self._flows[ticker_code] = flow

    def configure_failure(self, on: bool = True) -> None:
        self._raise = on

    def get_flows(self, ticker_codes: Sequence[str], as_of: date) -> dict[str, InvestorFlow]:
        _ = (ticker_codes, as_of)
        if self._raise:
            raise RuntimeError("fake flow provider failure")
        return {c: f for c, f in self._flows.items() if c in set(ticker_codes)}
