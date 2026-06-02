"""DART corp_code 매핑 포트.

DART API는 ticker(6자리 stock_code) 대신 corp_code(8자리)를 사용.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CorpCodeResolver(Protocol):
    """ticker_code → DART corp_code 매핑."""

    def get_corp_code(self, ticker_code: str) -> str | None: ...

    def get_all_mapping(self) -> dict[str, str]: ...
