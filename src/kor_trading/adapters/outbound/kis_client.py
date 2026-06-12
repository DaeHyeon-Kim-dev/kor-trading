"""한국투자증권(KIS) Open API 클라이언트.

OAuth 토큰 발급(/oauth2/tokenP) + 토큰 캐시 + 인증 GET 호출.
appkey/appsecret이 없으면 비활성(토큰 발급 시도 안 함).

도메인:
- 실전: https://openapi.koreainvestment.com:9443
- 모의: https://openapivts.koreainvestment.com:29443
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from pathlib import Path

log = structlog.get_logger()

_PROD_BASE = "https://openapi.koreainvestment.com:9443"
_VIRTUAL_BASE = "https://openapivts.koreainvestment.com:29443"
_DEFAULT_TIMEOUT_S = 15
_TOKEN_TTL_BUFFER_S = 600  # 만료 10분 전 갱신


class KisClient:
    def __init__(
        self,
        app_key: str | None,
        app_secret: str | None,
        *,
        virtual: bool = False,
        http_client: httpx.Client | None = None,
        token_cache_path: Path | None = None,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base = _VIRTUAL_BASE if virtual else _PROD_BASE
        self._client = (
            http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        )
        self._token: str | None = None
        # 만료 시각은 벽시계(epoch). 디스크 캐시로 프로세스 간 재사용 가능.
        self._token_expiry: float = 0.0
        self._cache_path = token_cache_path
        # 병렬 워커가 토큰을 각자 발급(KIS는 발급 1분당 1회 제한)하지 않도록 직렬화
        self._token_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._app_key and self._app_secret)

    def get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any] | None:
        """인증 GET 호출. 실패·비활성 시 None."""
        token = self._ensure_token()
        if token is None:
            return None
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self._app_key or "",
            "appsecret": self._app_secret or "",
            "tr_id": tr_id,
            "custtype": "P",
        }
        try:
            resp = self._client.get(f"{self._base}{path}", headers=headers, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as e:
            log.error("kis.http_failed", path=path, tr_id=tr_id, error=str(e))
            return None
        except ValueError as e:
            log.error("kis.bad_json", path=path, error=str(e))
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _ensure_token(self) -> str | None:
        if not self.enabled:
            return None
        if self._valid_in_memory():
            return self._token
        # 이중 체크 락: 한 워커만 발급하고 나머지는 캐시된 토큰을 재사용
        with self._token_lock:
            if self._valid_in_memory():
                return self._token
            # 디스크 캐시(프로세스 간 공유, 24h 유효) 우선 — 발급 스로틀 회피
            cached = self._load_cached_token()
            if cached is not None:
                self._token, self._token_expiry = cached
                return self._token
            return self._issue_token()

    def _valid_in_memory(self) -> bool:
        return bool(self._token and time.time() < self._token_expiry)

    def _load_cached_token(self) -> tuple[str, float] | None:
        if self._cache_path is None or not self._cache_path.exists():
            return None
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            token = str(data["access_token"])
            expiry = float(data["expiry_epoch"])
        except (OSError, ValueError, KeyError) as e:
            log.error("kis.token_cache_read_failed", error=str(e))
            return None
        if time.time() >= expiry:
            return None
        return token, expiry

    def _write_cached_token(self) -> None:
        if self._cache_path is None or self._token is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps({"access_token": self._token, "expiry_epoch": self._token_expiry}),
                encoding="utf-8",
            )
        except OSError as e:  # 캐시 쓰기 실패가 발급 자체를 막지 않도록
            log.error("kis.token_cache_write_failed", error=str(e))

    def _issue_token(self) -> str | None:
        body = {
            "grant_type": "client_credentials",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
        }
        try:
            resp = self._client.post(f"{self._base}/oauth2/tokenP", json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.error("kis.token_failed", error=str(e))
            return None
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 0))
        if not token:
            log.error("kis.token_missing", body_keys=list(data.keys()))
            return None
        self._token = str(token)
        self._token_expiry = time.time() + max(0, expires_in - _TOKEN_TTL_BUFFER_S)
        self._write_cached_token()
        log.info("kis.token_issued", expires_in=expires_in)
        return self._token
