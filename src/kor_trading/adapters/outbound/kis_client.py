"""한국투자증권(KIS) Open API 클라이언트.

OAuth 토큰 발급(/oauth2/tokenP) + 토큰 캐시 + 인증 GET 호출.
appkey/appsecret이 없으면 비활성(토큰 발급 시도 안 함).

도메인:
- 실전: https://openapi.koreainvestment.com:9443
- 모의: https://openapivts.koreainvestment.com:29443
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import structlog

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
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base = _VIRTUAL_BASE if virtual else _PROD_BASE
        self._client = (
            http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        )
        self._token: str | None = None
        self._token_expiry: float = 0.0
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
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        # 이중 체크 락: 한 워커만 발급하고 나머지는 캐시된 토큰을 재사용
        with self._token_lock:
            if self._token and time.monotonic() < self._token_expiry:
                return self._token
            return self._issue_token()

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
        self._token_expiry = time.monotonic() + max(0, expires_in - _TOKEN_TTL_BUFFER_S)
        log.info("kis.token_issued", expires_in=expires_in)
        return self._token
