"""KIS 기반 InvestorFlowProvider.

종목별 투자자매매동향(일별) API로 일자별 외국인·기관 순매수를 받아
최근 5일/20일 누적(거래대금 원 기준)을 계산한다.

API: /uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily (tr_id FHPTJ04160001)
응답 output2: 일자별 [stck_bsop_date, frgn_ntby_tr_pbmn(외국인 순매수 거래대금),
              orgn_ntby_tr_pbmn(기관 순매수 거래대금), ...]

필드명·단위는 실 응답(005930, 2025-06-02)으로 검증 완료:
*_ntby_tr_pbmn는 거래대금 백만원 단위. 스코어러는 부호만 사용하므로 단위 무관.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

import structlog

from kor_trading.domain.ports.investor_flow_provider import InvestorFlow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from kor_trading.adapters.outbound.kis_client import KisClient

log = structlog.get_logger()

_API_PATH = "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
_TR_ID = "FHPTJ04160001"
_MARKET_DIV = "J"  # KRX
_DEFAULT_WORKERS = 4
_PER_TICKER_TIMEOUT_S = 20

# output2 일자별 필드 (거래대금 백만원 단위) — 실 응답으로 검증 완료
_COL_FOREIGN = "frgn_ntby_tr_pbmn"
_COL_INSTITUTION = "orgn_ntby_tr_pbmn"

_DAYS_5 = 5
_DAYS_20 = 20


class KisInvestorFlowProvider:
    def __init__(self, client: KisClient, max_workers: int = _DEFAULT_WORKERS) -> None:
        self._client = client
        self._max_workers = max_workers

    def get_flows(self, ticker_codes: Sequence[str], as_of: date) -> dict[str, InvestorFlow]:
        if not self._client.enabled or not ticker_codes:
            return {}

        result: dict[str, InvestorFlow] = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._fetch_one, code, as_of): code for code in ticker_codes}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    flow = future.result(timeout=_PER_TICKER_TIMEOUT_S)
                    if flow is not None:
                        result[code] = flow
                except Exception as e:  # 한 종목 실패가 전체를 막지 않도록
                    log.error("kis_flow.failed", ticker=code, error=str(e))
        return result

    def _fetch_one(self, ticker_code: str, as_of: date) -> InvestorFlow | None:
        params = {
            "FID_COND_MRKT_DIV_CODE": _MARKET_DIV,
            "FID_INPUT_ISCD": ticker_code,
            "FID_INPUT_DATE_1": as_of.strftime("%Y%m%d"),
            "FID_ORG_ADJ_PRC": "",
            "FID_ETC_CLS_CODE": "",
        }
        payload = self._client.get(_API_PATH, _TR_ID, params)
        if payload is None:
            return None
        rows = payload.get("output2")
        if not isinstance(rows, list) or not rows:
            return None
        return _rows_to_flow(rows)


def _rows_to_flow(rows: list[dict[str, Any]]) -> InvestorFlow:
    """일자별 행(최신순 가정)에서 5일/20일 누적 순매수 합산."""
    foreign = [_to_int(r.get(_COL_FOREIGN)) for r in rows]
    institution = [_to_int(r.get(_COL_INSTITUTION)) for r in rows]
    return InvestorFlow(
        foreign_net_5d=_sum_first(foreign, _DAYS_5),
        foreign_net_20d=_sum_first(foreign, _DAYS_20),
        institution_net_5d=_sum_first(institution, _DAYS_5),
        institution_net_20d=_sum_first(institution, _DAYS_20),
    )


def _sum_first(values: list[int | None], n: int) -> int | None:
    valid = [v for v in values[:n] if v is not None]
    if not valid:
        return None
    return sum(valid)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in {"-", "--"}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None
