"""DART OpenAPI 기반 DisclosureProvider 어댑터.

API: https://opendart.fss.or.kr/api/list.json
- crtfc_key: API 키
- corp_code: 8자리 (KRX ticker 6자리와 별도)
- bgn_de / end_de: YYYYMMDD

ticker → corp_code 매핑은 외부에서 주입 (CORPCODE.xml 동기화는 별도 작업).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from kor_trading.domain.entities.disclosure import Disclosure, DisclosureSource

if TYPE_CHECKING:
    from datetime import date


log = structlog.get_logger()

_DART_BASE_URL = "https://opendart.fss.or.kr/api/list.json"
_DEFAULT_TIMEOUT_S = 10
_DEFAULT_PAGE_COUNT = 100  # DART 최대 100


class DartDisclosureProvider:
    """DART 공시 fetch."""

    def __init__(
        self,
        api_key: str,
        ticker_to_corp_code: dict[str, str],
        http_client: httpx.Client | None = None,
        base_url: str = _DART_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("DART api_key must not be empty")
        self._api_key = api_key
        self._mapping = dict(ticker_to_corp_code)
        self._client = (
            http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        )
        self._base_url = base_url

    def get_recent(self, ticker_code: str, end_date: date, lookback_days: int) -> list[Disclosure]:
        corp_code = self._mapping.get(ticker_code)
        if not corp_code:
            log.info("dart.ticker_unmapped", ticker=ticker_code)
            return []

        start_date = end_date - timedelta(days=lookback_days)
        params: dict[str, str | int] = {
            "crtfc_key": self._api_key,
            "corp_code": corp_code,
            "bgn_de": start_date.strftime("%Y%m%d"),
            "end_de": end_date.strftime("%Y%m%d"),
            "page_count": _DEFAULT_PAGE_COUNT,
        }

        try:
            response = self._client.get(self._base_url, params=params)
            response.raise_for_status()
            payload: Any = response.json()
        except httpx.HTTPError as e:
            log.error(
                "dart.http_failed",
                ticker=ticker_code,
                corp_code=corp_code,
                error=str(e),
            )
            return []

        return self._parse_payload(ticker_code, payload)

    def _parse_payload(self, ticker_code: str, payload: Any) -> list[Disclosure]:
        if not isinstance(payload, dict):  # pragma: no cover (defensive)
            log.warning("dart.invalid_payload", ticker=ticker_code)
            return []
        if payload.get("status") not in ("000", 0):
            log.info("dart.no_data", ticker=ticker_code, status=payload.get("status"))
            return []
        items = payload.get("list", [])
        if not isinstance(items, list):  # pragma: no cover (defensive)
            return []

        disclosures: list[Disclosure] = []
        for raw in items:
            try:
                disclosures.append(_to_disclosure(raw, ticker_code))
            except (ValueError, KeyError) as e:
                log.warning("dart.skip_item", ticker=ticker_code, error=str(e))
        return disclosures


def _to_disclosure(raw: dict[str, Any], ticker_code: str) -> Disclosure:
    rcept_no = raw["rcept_no"]
    rcept_dt = raw["rcept_dt"]  # "20260521"
    parsed_date = datetime.strptime(rcept_dt, "%Y%m%d").date()
    title = raw.get("report_nm", "").strip()
    if not title:
        raise ValueError(f"empty report_nm for {rcept_no}")
    return Disclosure(
        ticker_code=ticker_code,
        date=parsed_date,
        title=title,
        source=DisclosureSource.DART,
        source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
        report_type=raw.get("report_nm"),
    )
