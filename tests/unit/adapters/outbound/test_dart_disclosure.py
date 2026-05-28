"""DartDisclosureProvider 단위 테스트 — respx로 HTTP mock."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from kor_trading.adapters.outbound.dart_disclosure import DartDisclosureProvider
from kor_trading.domain.entities.disclosure import DisclosureSource
from kor_trading.domain.ports.disclosure_provider import DisclosureProvider

_BASE_URL = "https://opendart.fss.or.kr/api/list.json"
TICKER = "005930"
CORP_CODE = "00126380"


def _make_provider() -> DartDisclosureProvider:
    return DartDisclosureProvider(
        api_key="test-key",
        ticker_to_corp_code={TICKER: CORP_CODE},
        http_client=httpx.Client(),
    )


class TestConstruction:
    def test_rejects_empty_api_key(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            DartDisclosureProvider(api_key="", ticker_to_corp_code={})


class TestUnmappedTicker:
    def test_returns_empty_when_ticker_not_in_mapping(self) -> None:
        provider = DartDisclosureProvider(api_key="k", ticker_to_corp_code={})
        result = provider.get_recent("999999", date(2026, 5, 26), 7)
        assert result == []


class TestSuccessfulFetch:
    @respx.mock
    def test_returns_disclosures_from_list_response(self) -> None:
        respx.get(_BASE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "000",
                    "message": "정상",
                    "list": [
                        {
                            "rcept_no": "20260521000123",
                            "rcept_dt": "20260521",
                            "report_nm": "[기재정정]주요사항보고서(자기주식취득결정)",
                            "corp_code": CORP_CODE,
                            "corp_name": "삼성전자",
                        },
                        {
                            "rcept_no": "20260520000456",
                            "rcept_dt": "20260520",
                            "report_nm": "분기보고서",
                            "corp_code": CORP_CODE,
                            "corp_name": "삼성전자",
                        },
                    ],
                },
            )
        )
        provider = _make_provider()
        result = provider.get_recent(TICKER, date(2026, 5, 26), 7)
        assert len(result) == 2
        assert result[0].source == DisclosureSource.DART
        assert result[0].date == date(2026, 5, 21)
        assert "주요사항보고" in result[0].title


class TestStatusError:
    @respx.mock
    def test_returns_empty_when_status_not_zero(self) -> None:
        respx.get(_BASE_URL).mock(
            return_value=httpx.Response(
                200, json={"status": "013", "message": "조회된 데이타가 없습니다"}
            )
        )
        provider = _make_provider()
        assert provider.get_recent(TICKER, date(2026, 5, 26), 7) == []

    @respx.mock
    def test_returns_empty_when_http_error(self) -> None:
        respx.get(_BASE_URL).mock(return_value=httpx.Response(500))
        provider = _make_provider()
        assert provider.get_recent(TICKER, date(2026, 5, 26), 7) == []


class TestInvalidItems:
    @respx.mock
    def test_skips_items_with_empty_title(self) -> None:
        respx.get(_BASE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "1",
                            "rcept_dt": "20260521",
                            "report_nm": "정상보고서",
                        },
                        {
                            "rcept_no": "2",
                            "rcept_dt": "20260521",
                            "report_nm": "",
                        },
                    ],
                },
            )
        )
        provider = _make_provider()
        result = provider.get_recent(TICKER, date(2026, 5, 26), 7)
        assert len(result) == 1


class TestProtocolConformance:
    def test_implements_disclosure_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, DisclosureProvider)
