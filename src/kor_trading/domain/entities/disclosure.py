"""Disclosure 엔티티 — DART/뉴스 등에서 fetch한 원본 공시·뉴스 항목.

분석/가공 전 raw 데이터 컨테이너. Issue는 별도 분석 결과 엔티티.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from kor_trading.domain.entities.ticker import TICKER_CODE_LENGTH

if TYPE_CHECKING:
    from datetime import date


class DisclosureSource(StrEnum):
    DART = "DART"
    NAVER = "naver"
    RSS = "rss"


@dataclass(frozen=True, slots=True)
class Disclosure:
    ticker_code: str
    date: date
    title: str
    source: DisclosureSource
    source_url: str
    report_type: str | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("disclosure title must not be blank")
        if not (len(self.ticker_code) == TICKER_CODE_LENGTH and self.ticker_code.isdigit()):
            raise ValueError(f"invalid ticker_code: {self.ticker_code!r}")
