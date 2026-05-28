"""Telegram Bot API 기반 Notifier 어댑터.

API 문서: https://core.telegram.org/bots/api
- sendMessage (Markdown parse_mode)
- sendDocument (multipart)

4096자 제한: 자동 분할 (preserve newlines as boundaries).
"""

from __future__ import annotations

import time
from typing import Final

import httpx
import structlog

log = structlog.get_logger()

_DEFAULT_BASE_URL = "https://api.telegram.org"
_DEFAULT_TIMEOUT_S = 10
_TELEGRAM_MAX_MESSAGE_CHARS: Final[int] = 4096
_RATE_LIMIT_SLEEP_S = 0.1


class TelegramNotifier:
    """단일 chat_id로 메시지/문서 전송."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        http_client: httpx.Client | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        parse_mode: str = "Markdown",
    ) -> None:
        if not bot_token:
            raise ValueError("bot_token must not be empty")
        if not chat_id:
            raise ValueError("chat_id must not be empty")
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = (
            http_client if http_client is not None else httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        )
        self._base_url = base_url
        self._parse_mode = parse_mode

    def send_message(self, text: str) -> None:
        if not text:
            return
        chunks = _split_for_telegram(text, _TELEGRAM_MAX_MESSAGE_CHARS)
        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(_RATE_LIMIT_SLEEP_S)
            self._post_message(chunk)

    def send_document(self, filename: str, content: bytes, caption: str | None = None) -> None:
        url = f"{self._base_url}/bot{self._bot_token}/sendDocument"
        data: dict[str, str] = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption
        files = {"document": (filename, content, "text/markdown")}
        try:
            response = self._client.post(url, data=data, files=files)
            response.raise_for_status()
        except httpx.HTTPError as e:
            log.error("telegram.send_document_failed", filename=filename, error=str(e))
            raise

    def _post_message(self, text: str) -> None:
        url = f"{self._base_url}/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": self._parse_mode,
        }
        try:
            response = self._client.post(url, data=payload)
            response.raise_for_status()
        except httpx.HTTPError as e:
            log.error("telegram.send_message_failed", error=str(e))
            raise


def _split_for_telegram(text: str, limit: int) -> list[str]:
    """줄바꿈 우선으로 텔레그램 제한(4096자) 이내로 분할."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < 1:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:  # pragma: no branch (always True for typical inputs)
        chunks.append(remaining)
    return chunks
