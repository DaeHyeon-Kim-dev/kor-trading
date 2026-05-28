"""ticker_code → 종목명 변환 포트."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TickerNameResolver(Protocol):
    """6자리 ticker code → 한글 종목명. 없으면 None."""

    def get_name(self, ticker_code: str) -> str | None: ...
