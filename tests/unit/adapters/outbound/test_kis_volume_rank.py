"""KisVolumeRankProvider 테스트.

응답 스키마는 실 호출(2026-06-17, prod)로 검증한 KIS 거래량순위 API
(/uapi/domestic-stock/v1/quotations/volume-rank, tr_id FHPST01710000) 기준.
output 행: hts_kor_isnm, mksc_shrn_iscd, prdy_ctrt, acml_vol, acml_tr_pbmn,
stck_prpr, lstn_stcn ...
"""

from __future__ import annotations

from datetime import date

import httpx
import respx

from kor_trading.adapters.outbound.kis_client import KisClient
from kor_trading.adapters.outbound.kis_volume_rank import KisVolumeRankProvider
from kor_trading.domain.ports.intraday_rank_provider import IntradayRankProvider

_TOKEN_URL = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
_API_PATH = "/uapi/domestic-stock/v1/quotations/volume-rank"
_API_URL = f"https://openapi.koreainvestment.com:9443{_API_PATH}"
AS_OF = date(2026, 6, 17)


def _client() -> KisClient:
    return KisClient(app_key="k", app_secret="s", http_client=httpx.Client())


def _mock_token() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
    )


def _row(
    *,
    code: str,
    name: str,
    value: str,
    vol: str = "1000",
    price: str = "10000",
    ctrt: str = "1.50",
    shares: str = "1000000",
) -> dict[str, str]:
    return {
        "hts_kor_isnm": name,
        "mksc_shrn_iscd": code,
        "data_rank": "1",
        "stck_prpr": price,
        "prdy_ctrt": ctrt,
        "acml_vol": vol,
        "acml_tr_pbmn": value,
        "lstn_stcn": shares,
    }


def _ok(rows: list[dict[str, str]]) -> httpx.Response:
    return httpx.Response(200, json={"rt_cd": "0", "output": rows})


# ──────────────────────── 포트/비활성 ────────────────────────
class TestContract:
    def test_conforms_to_port(self) -> None:
        assert isinstance(KisVolumeRankProvider(client=_client()), IntradayRankProvider)

    def test_empty_when_client_disabled(self) -> None:
        c = KisClient(app_key=None, app_secret=None, http_client=httpx.Client())
        provider = KisVolumeRankProvider(client=c)
        assert provider.top_by_trading_value(("KOSPI", "KOSDAQ"), AS_OF) == []

    def test_empty_when_no_markets(self) -> None:
        assert KisVolumeRankProvider(client=_client()).top_by_trading_value((), AS_OF) == []


# ──────────────────────── 파싱/정렬/병합 ────────────────────────
class TestRanking:
    @respx.mock
    def test_parses_row_fields(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(
            return_value=_ok(
                [
                    _row(
                        code="000660",
                        name="SK하이닉스",
                        value="5564382421000",
                        vol="2307652",
                        price="2482000",
                        ctrt="4.28",
                        shares="712702365",
                    )
                ]
            )
        )
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert len(out) == 1
        s = out[0]
        assert s.ticker.code == "000660"
        assert s.ticker.name == "SK하이닉스"
        assert s.ticker.market == "KOSPI"
        assert s.close == 2482000
        assert s.change_pct == 4.28
        assert s.volume == 2307652
        assert s.trading_value == 5564382421000
        assert s.market_cap == 712702365 * 2482000  # 상장주수 * 현재가
        assert s.as_of == AS_OF

    @respx.mock
    def test_negative_change_pct(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(
            return_value=_ok([_row(code="005930", name="삼성전자", value="1", ctrt="-0.58")])
        )
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert out[0].change_pct == -0.58

    @respx.mock
    def test_merges_markets_and_sorts_by_value_desc(self) -> None:
        _mock_token()

        def handler(request: httpx.Request) -> httpx.Response:
            iscd = request.url.params.get("FID_INPUT_ISCD")
            if iscd == "0001":  # KOSPI
                return _ok(
                    [
                        _row(code="000660", name="하이닉스", value="500"),
                        _row(code="005930", name="삼성전자", value="300"),
                    ]
                )
            return _ok([_row(code="080220", name="제주반도체", value="400")])  # KOSDAQ

        respx.get(_API_URL).mock(side_effect=handler)
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(
            ("KOSPI", "KOSDAQ"), AS_OF
        )
        # 두 시장 병합 후 거래대금 내림차순
        assert [s.ticker.code for s in out] == ["000660", "080220", "005930"]
        assert [s.ticker.market for s in out] == ["KOSPI", "KOSDAQ", "KOSPI"]

    @respx.mock
    def test_respects_limit(self) -> None:
        _mock_token()
        rows = [_row(code=f"00000{i}", name=f"종목{i}", value=str(100 - i)) for i in range(1, 6)]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(
            ("KOSPI",), AS_OF, limit=3
        )
        assert len(out) == 3
        assert [s.trading_value for s in out] == [99, 98, 97]


# ──────────────────────── 격리/방어 ────────────────────────
class TestResilience:
    @respx.mock
    def test_skips_invalid_code(self) -> None:
        _mock_token()
        rows = [
            _row(code="ABC", name="잘못", value="100"),  # 6자리 숫자 아님
            _row(code="005930", name="삼성전자", value="50"),
        ]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in out] == ["005930"]

    @respx.mock
    def test_skips_blank_name(self) -> None:
        _mock_token()
        rows = [
            _row(code="005930", name="   ", value="100"),
            _row(code="000660", name="하이닉스", value="50"),
        ]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in out] == ["000660"]

    @respx.mock
    def test_skips_non_numeric_value(self) -> None:
        _mock_token()
        rows = [
            _row(code="005930", name="삼성전자", value="-"),
            _row(code="000660", name="하이닉스", value="50"),
        ]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in out] == ["000660"]

    @respx.mock
    def test_missing_market_cap_fields_default_zero(self) -> None:
        _mock_token()
        row = {
            "hts_kor_isnm": "삼성전자",
            "mksc_shrn_iscd": "005930",
            "stck_prpr": "10000",
            "prdy_ctrt": "1.0",
            "acml_vol": "100",
            "acml_tr_pbmn": "100",
            # lstn_stcn 누락
        }
        respx.get(_API_URL).mock(return_value=_ok([row]))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert out[0].market_cap == 0

    @respx.mock
    def test_output_not_list_yields_empty(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output": "oops"}))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert out == []

    @respx.mock
    def test_output_absent_yields_empty(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"rt_cd": "0"}))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert out == []

    def test_none_payload_yields_empty(self) -> None:
        class _NoneClient:
            enabled = True

            def get(self, path: str, tr_id: str, params: dict[str, str]) -> None:
                _ = (path, tr_id, params)

        provider = KisVolumeRankProvider(client=_NoneClient())  # type: ignore[arg-type]
        assert provider.top_by_trading_value(("KOSPI",), AS_OF) == []

    @respx.mock
    def test_one_market_failure_isolated(self) -> None:
        _mock_token()

        def handler(request: httpx.Request) -> httpx.Response:
            iscd = request.url.params.get("FID_INPUT_ISCD")
            if iscd == "0001":  # KOSPI 실패
                return httpx.Response(500)
            return _ok([_row(code="080220", name="제주반도체", value="400")])

        respx.get(_API_URL).mock(side_effect=handler)
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(
            ("KOSPI", "KOSDAQ"), AS_OF
        )
        # KOSPI 실패해도 KOSDAQ 결과는 반환
        assert [s.ticker.code for s in out] == ["080220"]

    def test_raising_client_isolated(self) -> None:
        class _RaisingClient:
            enabled = True

            def get(self, path: str, tr_id: str, params: dict[str, str]) -> None:
                _ = (path, tr_id, params)
                raise RuntimeError("boom")

        provider = KisVolumeRankProvider(client=_RaisingClient())  # type: ignore[arg-type]
        assert provider.top_by_trading_value(("KOSPI", "KOSDAQ"), AS_OF) == []

    @respx.mock
    def test_negative_price_skipped(self) -> None:
        # 음수가 들어오면 StockSnapshot 불변식 위반 → 해당 행 격리
        _mock_token()
        rows = [
            _row(code="005930", name="삼성전자", value="100", price="-100"),
            _row(code="000660", name="하이닉스", value="50"),
        ]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in out] == ["000660"]

    @respx.mock
    def test_non_numeric_int_field_skipped(self) -> None:
        _mock_token()
        rows = [
            _row(code="005930", name="삼성전자", value="N/A"),  # int 변환 불가
            _row(code="000660", name="하이닉스", value="50"),
        ]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert [s.ticker.code for s in out] == ["000660"]

    @respx.mock
    def test_change_pct_missing_or_invalid_defaults_zero(self) -> None:
        _mock_token()
        base = {
            "mksc_shrn_iscd": "005930",
            "hts_kor_isnm": "삼성전자",
            "stck_prpr": "10000",
            "acml_vol": "100",
            "acml_tr_pbmn": "300",
            "lstn_stcn": "1000",
        }
        rows = [
            {**base, "mksc_shrn_iscd": "005930"},  # prdy_ctrt 키 자체 없음 → None
            {**base, "mksc_shrn_iscd": "000660", "acml_tr_pbmn": "200", "prdy_ctrt": "-"},
            {**base, "mksc_shrn_iscd": "035720", "acml_tr_pbmn": "100", "prdy_ctrt": "N/A"},
        ]
        respx.get(_API_URL).mock(return_value=_ok(rows))
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(("KOSPI",), AS_OF)
        assert [s.change_pct for s in out] == [0.0, 0.0, 0.0]

    @respx.mock
    def test_unknown_market_skipped(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=_ok([_row(code="005930", name="삼성", value="1")]))
        # 매핑에 없는 시장은 호출하지 않고 생략
        out = KisVolumeRankProvider(client=_client()).top_by_trading_value(
            ("KOSPI", "KONEX"),  # type: ignore[arg-type]
            AS_OF,
        )
        assert [s.ticker.code for s in out] == ["005930"]
