"""실제 시스템 시계 어댑터 (KST)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")


class SystemClock:
    """KST 기준 현재 시각."""

    def now(self) -> datetime:
        return datetime.now(_KST)

    def today(self) -> date:
        return self.now().date()
