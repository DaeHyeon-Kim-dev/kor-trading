"""공시·뉴스 텍스트의 sentiment/impact/요약 분류 포트.

LLM 어댑터(Claude Code subprocess 등)가 구현. 도메인은 추상에만 의존.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from kor_trading.domain.entities.issue import Impact, Sentiment


@dataclass(frozen=True, slots=True)
class Classification:
    sentiment: Sentiment
    impact: Impact
    confidence: float
    summary: str


@runtime_checkable
class SentimentClassifier(Protocol):
    """공시 제목/본문 → 분류 결과. 실패 시 None."""

    def classify(self, title: str, *, context: str | None = None) -> Classification | None: ...
