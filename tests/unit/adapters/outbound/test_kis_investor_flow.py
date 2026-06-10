"""KisClient + KisInvestorFlowProvider 테스트."""

from __future__ import annotations

from datetime import date

import httpx
import respx

from kor_trading.adapters.outbound.kis_client import KisClient
from kor_trading.adapters.outbound.kis_investor_flow import KisInvestorFlowProvider
from kor_trading.domain.ports.investor_flow_provider import InvestorFlowProvider

_TOKEN_URL = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
_API_URL = (
    "https://openapi.koreainvestment.com:9443"
    "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
)
AS_OF = date(2025, 6, 2)


def _client() -> KisClient:
    return KisClient(app_key="k", app_secret="s", http_client=httpx.Client())


# ──────────────────────── KisClient ────────────────────────
class TestKisClientEnabled:
    def test_disabled_without_keys(self) -> None:
        c = KisClient(app_key=None, app_secret=None, http_client=httpx.Client())
        assert c.enabled is False
        assert c.get("/x", "TR", {}) is None

    def test_enabled_with_keys(self) -> None:
        assert _client().enabled is True


class TestKisToken:
    @respx.mock
    def test_issues_and_caches_token(self) -> None:
        token_route = respx.post(_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 86400})
        )
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": []}))
        c = _client()
        c.get("/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily", "T", {})
        c.get("/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily", "T", {})
        # 토큰은 1번만 발급 (캐시)
        assert token_route.call_count == 1

    @respx.mock
    def test_token_failure_returns_none(self) -> None:
        respx.post(_TOKEN_URL).mock(return_value=httpx.Response(403))
        assert _client().get("/x", "T", {}) is None

    @respx.mock
    def test_missing_token_field(self) -> None:
        respx.post(_TOKEN_URL).mock(return_value=httpx.Response(200, json={"no_token": 1}))
        assert _client().get("/x", "T", {}) is None

    @respx.mock
    def test_get_http_error_returns_none(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(500))
        assert (
            _client().get(
                "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily", "T", {}
            )
            is None
        )

    @respx.mock
    def test_get_non_dict_json_returns_none(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json=[1, 2, 3]))
        assert (
            _client().get(
                "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily", "T", {}
            )
            is None
        )

    @respx.mock
    def test_get_bad_json_returns_none(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, text="not json"))
        assert (
            _client().get(
                "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily", "T", {}
            )
            is None
        )


# ──────────────────────── Provider ────────────────────────
def _mock_token() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
    )


def _day(foreign: str, inst: str) -> dict[str, str]:
    return {"frgn_ntby_tr_pbmn": foreign, "orgn_ntby_tr_pbmn": inst}


class TestProvider:
    def test_conforms_to_port(self) -> None:
        provider = KisInvestorFlowProvider(client=_client())
        assert isinstance(provider, InvestorFlowProvider)

    def test_empty_when_client_disabled(self) -> None:
        c = KisClient(app_key=None, app_secret=None, http_client=httpx.Client())
        provider = KisInvestorFlowProvider(client=c)
        assert provider.get_flows(["005930"], AS_OF) == {}

    def test_empty_when_no_tickers(self) -> None:
        assert KisInvestorFlowProvider(client=_client()).get_flows([], AS_OF) == {}

    @respx.mock
    def test_aggregates_5d_20d(self) -> None:
        _mock_token()
        # 6일치 (최신순). 5일 합 vs 6일 일부
        rows = [
            _day("100", "10"),
            _day("100", "10"),
            _day("100", "10"),
            _day("100", "10"),
            _day("100", "10"),
            _day("100", "10"),
        ]
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": rows}))
        provider = KisInvestorFlowProvider(client=_client())
        flows = provider.get_flows(["005930"], AS_OF)
        assert flows["005930"].foreign_net_5d == 500  # 100*5
        assert flows["005930"].foreign_net_20d == 600  # 100*6 (20 이내 전체)
        assert flows["005930"].institution_net_5d == 50

    @respx.mock
    def test_skips_ticker_with_no_output(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": []}))
        provider = KisInvestorFlowProvider(client=_client())
        assert provider.get_flows(["005930"], AS_OF) == {}

    @respx.mock
    def test_handles_invalid_numeric(self) -> None:
        _mock_token()
        rows = [_day("-", "abc"), _day("100", "10")]
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": rows}))
        provider = KisInvestorFlowProvider(client=_client())
        flows = provider.get_flows(["005930"], AS_OF)
        # 잘못된 값은 제외, 유효값만 합산
        assert flows["005930"].foreign_net_5d == 100
        assert flows["005930"].institution_net_5d == 10

    @respx.mock
    def test_output2_not_list_skipped(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": "oops"}))
        provider = KisInvestorFlowProvider(client=_client())
        assert provider.get_flows(["005930"], AS_OF) == {}

    @respx.mock
    def test_output2_absent_skipped(self) -> None:
        _mock_token()
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"rt_cd": "0"}))
        provider = KisInvestorFlowProvider(client=_client())
        assert provider.get_flows(["005930"], AS_OF) == {}

    @respx.mock
    def test_non_numeric_string_excluded(self) -> None:
        _mock_token()
        # 숫자로 변환 불가한 문자열 → 제외
        rows = [{"frgn_ntby_tr_pbmn": "N/A", "orgn_ntby_tr_pbmn": "10"}]
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": rows}))
        provider = KisInvestorFlowProvider(client=_client())
        flows = provider.get_flows(["005930"], AS_OF)
        assert flows["005930"].foreign_net_5d is None
        assert flows["005930"].institution_net_5d == 10

    @respx.mock
    def test_all_invalid_yields_none_fields(self) -> None:
        _mock_token()
        rows = [_day("-", "-"), _day("--", "--")]
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": rows}))
        provider = KisInvestorFlowProvider(client=_client())
        flows = provider.get_flows(["005930"], AS_OF)
        # 행은 있지만 유효 숫자 없음 → 모든 누적 None
        assert flows["005930"].foreign_net_5d is None
        assert flows["005930"].institution_net_5d is None

    def test_none_payload_skipped(self) -> None:
        # client.get이 None(인증 실패/에러) → 해당 종목 생략
        class _NoneClient:
            enabled = True

            def get(self, path: str, tr_id: str, params: dict[str, str]) -> None:
                _ = (path, tr_id, params)

        provider = KisInvestorFlowProvider(client=_NoneClient())  # type: ignore[arg-type]
        assert provider.get_flows(["005930"], AS_OF) == {}

    @respx.mock
    def test_none_value_in_row(self) -> None:
        _mock_token()
        rows = [{"frgn_ntby_tr_pbmn": None, "orgn_ntby_tr_pbmn": "10"}]
        respx.get(_API_URL).mock(return_value=httpx.Response(200, json={"output2": rows}))
        flows = KisInvestorFlowProvider(client=_client()).get_flows(["005930"], AS_OF)
        assert flows["005930"].foreign_net_5d is None
        assert flows["005930"].institution_net_5d == 10

    def test_one_ticker_failure_isolated(self) -> None:
        # client.get이 예외를 던지는 stub
        class _RaisingClient:
            enabled = True

            def get(self, path: str, tr_id: str, params: dict[str, str]) -> None:
                _ = (path, tr_id, params)
                raise RuntimeError("boom")

        provider = KisInvestorFlowProvider(client=_RaisingClient())  # type: ignore[arg-type]
        # 예외는 격리되어 빈 결과
        assert provider.get_flows(["005930", "000660"], AS_OF) == {}
