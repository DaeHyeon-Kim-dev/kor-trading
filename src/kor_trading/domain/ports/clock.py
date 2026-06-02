"""시간 추상화 포트 — 테스트 가능성 위해 now/today를 주입."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date, datetime


@runtime_checkable
class Clock(Protocol):
    """현재 시각(KST 기준) 제공. 테스트에서는 FixedClock 사용."""

    def now(self) -> datetime: ...

    def today(self) -> date: ...
