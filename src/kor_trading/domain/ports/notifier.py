"""알림 전송 포트 (텔레그램 등)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """단일 채널 메시지/파일 전송."""

    def send_message(self, text: str) -> None: ...

    def send_document(self, filename: str, content: bytes, caption: str | None = None) -> None: ...
