"""DartCorpCodeResolver 테스트 (respx HTTP mock + 디스크 캐시)."""

from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from kor_trading.adapters.outbound.dart_corp_code_resolver import DartCorpCodeResolver
from kor_trading.domain.ports.corp_code_resolver import CorpCodeResolver

if TYPE_CHECKING:
    from pathlib import Path


_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

_SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<result>
    <list>
        <corp_code>00126380</corp_code>
        <corp_name>삼성전자</corp_name>
        <stock_code>005930</stock_code>
        <modify_date>20231229</modify_date>
    </list>
    <list>
        <corp_code>00164742</corp_code>
        <corp_name>카카오</corp_name>
        <stock_code>035720</stock_code>
        <modify_date>20231229</modify_date>
    </list>
    <list>
        <corp_code>99999999</corp_code>
        <corp_name>비상장기업</corp_name>
        <stock_code></stock_code>
        <modify_date>20231229</modify_date>
    </list>
    <list>
        <corp_code></corp_code>
        <corp_name>코드없음</corp_name>
        <stock_code>012345</stock_code>
        <modify_date>20231229</modify_date>
    </list>
</result>
"""


def _make_zip(xml_content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml_content)
    return buf.getvalue()


@pytest.fixture
def resolver(tmp_path: Path) -> DartCorpCodeResolver:
    cache = tmp_path / "corp_code.json"
    return DartCorpCodeResolver(api_key="test", cache_path=cache, http_client=httpx.Client())


class TestConstruction:
    def test_rejects_empty_api_key(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="api_key"):
            DartCorpCodeResolver(api_key="", cache_path=tmp_path / "x.json")


class TestFetchAndParse:
    @respx.mock
    def test_parses_zip_and_returns_mapping(self, resolver: DartCorpCodeResolver) -> None:
        respx.get(_URL).mock(return_value=httpx.Response(200, content=_make_zip(_SAMPLE_XML)))

        assert resolver.get_corp_code("005930") == "00126380"
        assert resolver.get_corp_code("035720") == "00164742"
        # 비상장(stock_code 빈)은 제외
        assert resolver.get_corp_code("99999999") is None

    @respx.mock
    def test_get_all_mapping_returns_full_dict(self, resolver: DartCorpCodeResolver) -> None:
        respx.get(_URL).mock(return_value=httpx.Response(200, content=_make_zip(_SAMPLE_XML)))
        mapping = resolver.get_all_mapping()
        assert mapping == {"005930": "00126380", "035720": "00164742"}


class TestDiskCache:
    @respx.mock
    def test_writes_cache_after_fetch(self, resolver: DartCorpCodeResolver, tmp_path: Path) -> None:
        respx.get(_URL).mock(return_value=httpx.Response(200, content=_make_zip(_SAMPLE_XML)))
        resolver.get_all_mapping()
        cache = tmp_path / "corp_code.json"
        assert cache.exists()
        loaded = json.loads(cache.read_text(encoding="utf-8"))
        assert loaded["005930"] == "00126380"

    @respx.mock
    def test_loads_from_cache_without_http_call(self, tmp_path: Path) -> None:
        cache = tmp_path / "corp_code.json"
        cache.write_text(json.dumps({"005930": "00126380"}), encoding="utf-8")
        route = respx.get(_URL).mock(return_value=httpx.Response(200))

        r = DartCorpCodeResolver(api_key="k", cache_path=cache, http_client=httpx.Client())
        assert r.get_corp_code("005930") == "00126380"
        assert not route.called  # 캐시 hit → HTTP 호출 없음

    @respx.mock
    def test_corrupted_cache_falls_back_to_fetch(self, tmp_path: Path) -> None:
        cache = tmp_path / "corp_code.json"
        cache.write_text("garbage json", encoding="utf-8")
        respx.get(_URL).mock(return_value=httpx.Response(200, content=_make_zip(_SAMPLE_XML)))

        r = DartCorpCodeResolver(api_key="k", cache_path=cache, http_client=httpx.Client())
        assert r.get_corp_code("005930") == "00126380"


class TestErrorHandling:
    @respx.mock
    def test_http_error_returns_empty_mapping(self, resolver: DartCorpCodeResolver) -> None:
        respx.get(_URL).mock(return_value=httpx.Response(500))
        assert resolver.get_all_mapping() == {}

    @respx.mock
    def test_invalid_zip_returns_empty(self, resolver: DartCorpCodeResolver) -> None:
        respx.get(_URL).mock(return_value=httpx.Response(200, content=b"not a zip"))
        assert resolver.get_all_mapping() == {}

    @respx.mock
    def test_zip_without_xml_returns_empty(self, resolver: DartCorpCodeResolver) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.txt", "no xml here")
        respx.get(_URL).mock(return_value=httpx.Response(200, content=buf.getvalue()))
        assert resolver.get_all_mapping() == {}


class TestForceRefresh:
    @respx.mock
    def test_force_refresh_refetches(self, tmp_path: Path) -> None:
        cache = tmp_path / "corp_code.json"
        cache.write_text(json.dumps({"old": "code"}), encoding="utf-8")

        respx.get(_URL).mock(return_value=httpx.Response(200, content=_make_zip(_SAMPLE_XML)))
        r = DartCorpCodeResolver(api_key="k", cache_path=cache, http_client=httpx.Client())
        r.force_refresh()
        # 캐시 덮어쓰기
        loaded = json.loads(cache.read_text(encoding="utf-8"))
        assert "005930" in loaded
        assert "old" not in loaded


class TestProtocolConformance:
    def test_conforms_to_port(self, resolver: DartCorpCodeResolver) -> None:
        assert isinstance(resolver, CorpCodeResolver)
