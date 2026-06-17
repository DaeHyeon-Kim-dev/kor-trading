"""KIS 거래량순위 API 기반 IntradayRankProvider.

장중 실시간 거래대금 상위 종목을 시장별로 조회해 병합·정렬한다.
KRX 일별매매정보(EOD)와 달리 '지금 이 순간'의 순위를 준다.

API: /uapi/domestic-stock/v1/quotations/volume-rank (tr_id FHPST01710000)
- FID_BLNG_CLS_CODE="3" → 거래금액(거래대금)순
- FID_INPUT_ISCD: 0001 코스피 / 1001 코스닥 (시장별로 따로 호출해 시장 라벨 확보)
- 응답 output: 시장당 상위 30행

필드(실 응답 2026-06-17·prod 검증):
- mksc_shrn_iscd 종목코드 / hts_kor_isnm 종목명 / stck_prpr 현재가
- prdy_ctrt 등락률(부호 포함) / acml_vol 누적거래량 / acml_tr_pbmn 누적거래대금(원)
- lstn_stcn 상장주수 → 시총 = 상장주수 * 현재가
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

import structlog

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import TICKER_CODE_LENGTH, Market, Ticker

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.adapters.outbound.kis_client import KisClient

log = structlog.get_logger()

_API_PATH = "/uapi/domestic-stock/v1/quotations/volume-rank"
_TR_ID = "FHPST01710000"
_MARKET_DIV = "J"  # 주식
_SCR_DIV = "20171"  # 거래량순위 화면 고유키
_BLNG_VALUE = "3"  # 소속구분: 거래금액(거래대금)순
_DEFAULT_LIMIT = 20
_DEFAULT_WORKERS = 2
_PER_MARKET_TIMEOUT_S = 20

# 도메인 Market → KIS FID_INPUT_ISCD
_MARKET_ISCD: dict[str, str] = {"KOSPI": "0001", "KOSDAQ": "1001"}

_COL_CODE = "mksc_shrn_iscd"
_COL_NAME = "hts_kor_isnm"
_COL_PRICE = "stck_prpr"
_COL_CHANGE_RT = "prdy_ctrt"
_COL_VOLUME = "acml_vol"
_COL_VALUE = "acml_tr_pbmn"
_COL_SHARES = "lstn_stcn"


class KisVolumeRankProvider:
    def __init__(self, client: KisClient, max_workers: int = _DEFAULT_WORKERS) -> None:
        self._client = client
        self._max_workers = max_workers

    def top_by_trading_value(
        self, markets: tuple[Market, ...], as_of: date, limit: int = _DEFAULT_LIMIT
    ) -> list[StockSnapshot]:
        targets = [m for m in markets if m in _MARKET_ISCD]
        if not self._client.enabled or not targets:
            return []

        merged: list[StockSnapshot] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._fetch_market, m, as_of): m for m in targets}
            for future in as_completed(futures):
                market = futures[future]
                try:
                    merged.extend(future.result(timeout=_PER_MARKET_TIMEOUT_S))
                except Exception as e:  # 한 시장 실패가 전체를 막지 않도록
                    log.error("kis_value_rank.failed", market=market, error=str(e))

        merged.sort(key=lambda s: s.trading_value, reverse=True)
        return merged[:limit]

    def _fetch_market(self, market: Market, as_of: date) -> list[StockSnapshot]:
        params = {
            "FID_COND_MRKT_DIV_CODE": _MARKET_DIV,
            "FID_COND_SCR_DIV_CODE": _SCR_DIV,
            "FID_INPUT_ISCD": _MARKET_ISCD[market],
            "FID_DIV_CLS_CODE": "0",  # 전체
            "FID_BLNG_CLS_CODE": _BLNG_VALUE,
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
        }
        payload = self._client.get(_API_PATH, _TR_ID, params)
        if payload is None:
            return []
        rows = payload.get("output")
        if not isinstance(rows, list):
            return []
        snaps = [_row_to_snapshot(r, market, as_of) for r in rows]
        return [s for s in snaps if s is not None]


def _row_to_snapshot(row: dict[str, Any], market: Market, as_of: date) -> StockSnapshot | None:
    code = str(row.get(_COL_CODE, "")).strip()
    if not (len(code) == TICKER_CODE_LENGTH and code.isdigit()):
        return None
    name = str(row.get(_COL_NAME, "")).strip()
    if not name:
        return None
    close = _to_int(row.get(_COL_PRICE))
    volume = _to_int(row.get(_COL_VOLUME))
    value = _to_int(row.get(_COL_VALUE))
    if close is None or volume is None or value is None:
        return None
    shares = _to_int(row.get(_COL_SHARES)) or 0
    try:
        return StockSnapshot(
            ticker=Ticker(code=code, name=name, market=market),
            as_of=as_of,
            close=close,
            change_pct=_to_float(row.get(_COL_CHANGE_RT)),
            volume=volume,
            trading_value=value,
            market_cap=shares * close,
        )
    except ValueError:  # 음수 등 도메인 불변식 위반 행은 격리
        return None


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


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    s = str(value).strip().replace(",", "")
    if not s or s in {"-", "--"}:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0
