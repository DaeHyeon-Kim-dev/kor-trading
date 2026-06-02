"""in-memory FakeSentimentClassifier — 제목별 고정 분류 반환."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kor_trading.domain.ports.sentiment_classifier import Classification


class FakeSentimentClassifier:
    def __init__(self, default: Classification | None = None) -> None:
        self._by_title: dict[str, Classification | None] = {}
        self._default = default

    def set_for_title(self, title: str, classification: Classification | None) -> None:
        self._by_title[title] = classification

    def classify(self, title: str, *, context: str | None = None) -> Classification | None:
        _ = context
        if title in self._by_title:
            return self._by_title[title]
        return self._default
