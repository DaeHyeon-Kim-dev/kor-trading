"""KrxOpenApiClient + KrxOpenApiMarketSnapshotProvider 테스트."""

from __future__ import annotations

from datetime import date

import httpx
import respx

from kor_trading.adapters.outbound.krx_openapi_client import KrxOpenApiClient
from kor_trading.adapters.outbound.krx_openapi_market_snapshot import (
    KrxOpenApiMarketSnapshotProvider,
)
from kor_trading.domain.ports.market_snapshot_provider import MarketSnapshotProvider

_KOSPI_URL = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"


def _row(code: str, name: str = "삼성전자", close: str = "78500", **over: str) -> dict[str, str]:
    base = {
        "BAS_DD": "20250102",
        "ISU_CD": code,
        "ISU_NM": name,
        "MKT_NM": "KOSPI",
        "TDD_CLSPRC": close,
        "FLUC_RT": "5.2",
        "TDD_OPNPRC": "78000",
        "TDD_HGPRC": "79000",
        "TDD_LWPRC": "77500",
        "ACC_TRDVOL": "25300000",
        "ACC_TRDVAL": "1980000000000",
        "MKTCAP": "469000000000000",
        "LIST_SHRS": "5969782550",
    }
    base.update(over)
    return base


# ──────────────────────── client ────────────────────────
class TestClient:
    def test_empty_auth_key_returns_empty_without_call(self) -> None:
        client = KrxOpenApiClient(auth_key="", http_client=httpx.Client())
        assert client.get_daily_trades("KOSPI", "20250102") == []

    @respx.mock
    def test_get_daily_trades_parses_outblock(self) -> None:
        respx.get(_KOSPI_URL).mock(
            return_value=httpx.Response(200, json={"OutBlock_1": [_row("005930")]})
        )
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        rows = client.get_daily_trades("KOSPI", "20250102")
        assert len(rows) == 1
        assert rows[0]["ISU_CD"] == "005930"

    @respx.mock
    def test_sends_auth_key_header(self) -> None:
        route = respx.get(_KOSPI_URL).mock(
            return_value=httpx.Response(200, json={"OutBlock_1": []})
        )
        client = KrxOpenApiClient(auth_key="secret-key", http_client=httpx.Client())
        client.get_daily_trades("KOSPI", "20250102")
        assert route.calls.last.request.headers["AUTH_KEY"] == "secret-key"

    @respx.mock
    def test_http_error_returns_empty(self) -> None:
        respx.get(_KOSPI_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        assert client.get_daily_trades("KOSPI", "20250102") == []

    @respx.mock
    def test_empty_outblock_for_holiday(self) -> None:
        respx.get(_KOSPI_URL).mock(return_value=httpx.Response(200, json={"OutBlock_1": []}))
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        assert client.get_daily_trades("KOSPI", "20250101") == []

    @respx.mock
    def test_non_json_body_returns_empty(self) -> None:
        respx.get(_KOSPI_URL).mock(return_value=httpx.Response(200, text="not json"))
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        assert client.get_daily_trades("KOSPI", "20250102") == []

    @respx.mock
    def test_outblock_not_list_returns_empty(self) -> None:
        respx.get(_KOSPI_URL).mock(return_value=httpx.Response(200, json={"OutBlock_1": "oops"}))
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        assert client.get_daily_trades("KOSPI", "20250102") == []

    def test_unknown_market_returns_empty(self) -> None:
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        assert client.get_daily_trades("KONEX", "20250102") == []  # type: ignore[arg-type]


# ──────────────────────── provider ────────────────────────
class _FakeClient:
    def __init__(self, by_date: dict[tuple[str, str], list[dict[str, str]]]) -> None:
        # key: (market, basDd)
        self._by_date = by_date
        self.calls: list[tuple[str, str]] = []

    def get_daily_trades(self, market: str, bas_dd: str) -> list[dict[str, str]]:
        self.calls.append((market, bas_dd))
        return self._by_date.get((market, bas_dd), [])


class TestProviderConformance:
    def test_conforms_to_port(self) -> None:
        client = KrxOpenApiClient(auth_key="k", http_client=httpx.Client())
        provider = KrxOpenApiMarketSnapshotProvider(client=client)
        assert isinstance(provider, MarketSnapshotProvider)


class TestProviderMapping:
    def test_maps_fields_including_name_and_marcap(self) -> None:
        fake = _FakeClient({("KOSPI", "20250102"): [_row("005930", "삼성전자")]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 2))
        assert len(snaps) == 1
        s = snaps[0]
        assert s.ticker.code == "005930"
        assert s.ticker.name == "삼성전자"  # 종목명 응답에서 직접
        assert s.close == 78500
        assert s.change_pct == 5.2
        assert s.trading_value == 1980000000000
        assert s.market_cap == 469000000000000

    def test_skips_invalid_code(self) -> None:
        fake = _FakeClient({("KOSPI", "20250102"): [_row("005930"), _row("ABCDEF"), _row("12345")]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 2))
        assert [s.ticker.code for s in snaps] == ["005930"]

    def test_skips_empty_numeric(self) -> None:
        fake = _FakeClient({("KOSPI", "20250102"): [_row("005930", close=""), _row("000660")]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 2))
        assert [s.ticker.code for s in snaps] == ["000660"]

    def test_empty_change_rt_becomes_zero(self) -> None:
        fake = _FakeClient({("KOSPI", "20250102"): [_row("005930", FLUC_RT="")]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 2))
        assert snaps[0].change_pct == 0.0

    def test_blank_name_falls_back_to_code(self) -> None:
        fake = _FakeClient({("KOSPI", "20250102"): [_row("005930", name="   ")]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 2))
        assert snaps[0].ticker.name == "005930"

    def test_none_values_skipped_and_zeroed(self) -> None:
        # 거래대금 None → _int raise → skip / 등락률 None → _float 0.0
        row_bad_amount = _row("005930")
        row_bad_amount["ACC_TRDVAL"] = None  # type: ignore[assignment]
        row_ok = _row("000660")
        row_ok["FLUC_RT"] = None  # type: ignore[assignment]
        fake = _FakeClient({("KOSPI", "20250102"): [row_bad_amount, row_ok]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 2))
        assert [s.ticker.code for s in snaps] == ["000660"]
        assert snaps[0].change_pct == 0.0


class TestProviderDateAdjust:
    def test_falls_back_to_recent_business_day(self) -> None:
        # 요청일(1/4 토)은 빈, 1/2(목)에 데이터
        fake = _FakeClient({("KOSPI", "20250102"): [_row("005930")]})
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 4))
        assert len(snaps) == 1
        assert snaps[0].as_of == date(2025, 1, 2)  # 실제 거래일로 보정

    def test_returns_empty_when_no_data_in_lookback(self) -> None:
        fake = _FakeClient({})  # 아무 날짜도 데이터 없음
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI",), date(2025, 1, 4))
        assert snaps == []


class TestMultiMarket:
    def test_concatenates_kospi_kosdaq(self) -> None:
        fake = _FakeClient(
            {
                ("KOSPI", "20250102"): [_row("005930")],
                ("KOSDAQ", "20250102"): [_row("035720", "에코프로")],
            }
        )
        provider = KrxOpenApiMarketSnapshotProvider(client=fake)  # type: ignore[arg-type]
        snaps = provider.get_market_snapshots(("KOSPI", "KOSDAQ"), date(2025, 1, 2))
        codes = {s.ticker.code for s in snaps}
        assert codes == {"005930", "035720"}
