"""KRX OPEN API (data-dbg.krx.co.kr) HTTP 클라이언트.

공식 REST API. AUTH_KEY 헤더 인증 (로그인 불필요).
일별매매정보(유가/코스닥)는 종가·등락률·OHLC·거래량·거래대금·시총·종목명을
한 번에 제공한다.

API: https://data-dbg.krx.co.kr/svc/apis/sto/{stk|ksq}_bydd_trd?basDd=YYYYMMDD
응답: {"OutBlock_1": [ {BAS_DD, ISU_CD, ISU_NM, MKT_NM, TDD_CLSPRC, FLUC_RT,
       TDD_OPNPRC, TDD_HGPRC, TDD_LWPRC, ACC_TRDVOL, ACC_TRDVAL, MKTCAP,
       LIST_SHRS, ...}, ... ]}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from kor_trading.domain.entities.ticker import Market

log = structlog.get_logger()

_BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"
_DEFAULT_TIMEOUT_S = 30

# 도메인 Market → KRX 일별매매정보 엔드포인트
_MARKET_ENDPOINT: dict[str, str] = {
    "KOSPI": "sto/stk_bydd_trd",
    "KOSDAQ": "sto/ksq_bydd_trd",
}


class KrxOpenApiClient:
    """KRX OPEN API 호출 + AUTH_KEY 인증."""

    def __init__(
        self,
        auth_key: str,
        http_client: httpx.Client | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        self._auth_key = auth_key
        self._client = (
            http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        )
        self._base_url = base_url

    def get_daily_trades(self, market: Market, bas_dd: str) -> list[dict[str, Any]]:
        """특정 시장의 basDd(YYYYMMDD) 일별매매정보 전종목.

        휴장일/미래 일자는 빈 리스트. 인증/HTTP 오류도 빈 리스트(격리).
        auth_key가 없으면 호출하지 않고 빈 리스트.
        """
        if not self._auth_key:
            log.warning("krx_openapi.no_auth_key")
            return []
        endpoint = _MARKET_ENDPOINT.get(market)
        if endpoint is None:
            log.warning("krx_openapi.unknown_market", market=market)
            return []

        url = f"{self._base_url}/{endpoint}"
        try:
            resp = self._client.get(
                url,
                headers={"AUTH_KEY": self._auth_key},
                params={"basDd": bas_dd},
                follow_redirects=True,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as e:
            log.error("krx_openapi.http_failed", market=market, bas_dd=bas_dd, error=str(e))
            return []
        except ValueError as e:  # JSON decode
            log.error("krx_openapi.bad_json", market=market, bas_dd=bas_dd, error=str(e))
            return []

        rows = payload.get("OutBlock_1", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return []
        return rows
