"""DART CORPCODE.xml 다운로드 + 파싱 + 디스크 캐시.

API: https://opendart.fss.or.kr/api/corpCode.xml
- ZIP 파일 반환 (CORPCODE.xml 포함)
- corp_code(8) ↔ stock_code(6, 종목코드) ↔ corp_name 매핑

캐시: data/cache/corp_code.json (TTL 1일 권장, 외부 호출자가 관리).
"""

from __future__ import annotations

import io
import json
import zipfile
from threading import Lock
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import httpx
import structlog

if TYPE_CHECKING:
    from pathlib import Path


log = structlog.get_logger()

_DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
_DEFAULT_TIMEOUT_S = 30
_TICKER_CODE_LENGTH = 6


class DartCorpCodeResolver:
    """DART corpCode.xml fetch + 디스크 캐시.

    캐시 파일 존재 시 디스크에서 즉시 로드. 갱신은 외부 트리거(파일 삭제) 또는
    `force_refresh()` 호출.
    """

    def __init__(
        self,
        api_key: str,
        cache_path: Path,
        http_client: httpx.Client | None = None,
        base_url: str = _DART_CORPCODE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("DART api_key must not be empty")
        self._api_key = api_key
        self._cache_path = cache_path
        self._client = (
            http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        )
        self._base_url = base_url
        self._mapping: dict[str, str] | None = None
        self._lock = Lock()

    def get_corp_code(self, ticker_code: str) -> str | None:
        return self.get_all_mapping().get(ticker_code)

    def get_all_mapping(self) -> dict[str, str]:
        if self._mapping is None:
            self._load()
        return dict(self._mapping or {})

    def force_refresh(self) -> None:
        """캐시 무시하고 다시 fetch."""
        with self._lock:
            self._mapping = None
            self._fetch_and_cache()

    def _load(self) -> None:
        with self._lock:
            if self._mapping is not None:  # pragma: no cover (race condition)
                return
            if self._cache_path.exists():
                try:
                    self._mapping = json.loads(self._cache_path.read_text(encoding="utf-8"))
                    log.info("corp_code.loaded_from_cache", count=len(self._mapping or {}))
                    return
                except (OSError, json.JSONDecodeError) as e:
                    log.warning("corp_code.cache_corrupted", error=str(e))
            self._fetch_and_cache()

    def _fetch_and_cache(self) -> None:
        try:
            response = self._client.get(self._base_url, params={"crtfc_key": self._api_key})
            response.raise_for_status()
            zip_bytes = response.content
        except httpx.HTTPError as e:
            log.error("corp_code.fetch_failed", error=str(e))
            self._mapping = {}
            return

        try:
            mapping = _parse_zip(zip_bytes)
        except (zipfile.BadZipFile, ET.ParseError, KeyError) as e:
            log.error("corp_code.parse_failed", error=str(e))
            self._mapping = {}
            return

        self._mapping = mapping
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            log.info("corp_code.cached", count=len(mapping), path=str(self._cache_path))
        except OSError as e:  # pragma: no cover (디스크 쓰기 실패 fail-soft)
            log.warning("corp_code.cache_write_failed", error=str(e))


def _parse_zip(zip_bytes: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        xml_name = next((n for n in names if n.lower().endswith(".xml")), None)
        if xml_name is None:
            raise KeyError("CORPCODE.xml not found in DART response")
        with zf.open(xml_name) as f:
            xml_bytes = f.read()

    root = ET.fromstring(xml_bytes)
    mapping: dict[str, str] = {}
    for item in root.iter("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if not corp_code:
            continue
        if len(stock_code) == _TICKER_CODE_LENGTH and stock_code.isdigit():
            mapping[stock_code] = corp_code
    return mapping
