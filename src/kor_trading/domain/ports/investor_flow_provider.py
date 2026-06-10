"""투자자별 수급(외국인/기관 누적 순매수) fetch 포트."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date


@dataclass(frozen=True, slots=True)
class InvestorFlow:
    """한 종목의 외국인·기관 누적 순매수(거래대금, 백만원 단위).

    KIS investor-trade-by-stock-daily의 *_ntby_tr_pbmn 필드는 백만원 단위다.
    스코어러는 부호(매수/매도)만 사용하므로 단위 스케일은 점수에 영향 없음.
    """

    foreign_net_5d: int | None = None
    foreign_net_20d: int | None = None
    institution_net_5d: int | None = None
    institution_net_20d: int | None = None


@runtime_checkable
class InvestorFlowProvider(Protocol):
    """종목 리스트의 외국인·기관 수급을 조회.

    KIS 등 종목별 조회 어댑터가 구현. 반환: {ticker_code: InvestorFlow}
    조회 실패·미제공 종목은 결과에서 생략한다.
    """

    def get_flows(self, ticker_codes: Sequence[str], as_of: date) -> dict[str, InvestorFlow]: ...
