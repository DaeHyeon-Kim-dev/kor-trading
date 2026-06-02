"""SystemClock + FixedClock(테스트 더블) 테스트."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from kor_trading.domain.ports.clock import Clock
from kor_trading.infrastructure.clock import SystemClock
from tests.fakes.fixed_clock import FixedClock

_KST = ZoneInfo("Asia/Seoul")


class TestSystemClock:
    def test_now_is_kst_aware(self) -> None:
        clock = SystemClock()
        now = clock.now()
        assert now.tzinfo is not None
        # KST offset = +9h
        assert now.utcoffset() is not None
        assert now.utcoffset().total_seconds() == 9 * 3600  # type: ignore[union-attr]

    def test_today_matches_now_date(self) -> None:
        clock = SystemClock()
        assert clock.today() == clock.now().date()

    def test_conforms_to_clock_protocol(self) -> None:
        assert isinstance(SystemClock(), Clock)


class TestFixedClock:
    def test_returns_fixed_time(self) -> None:
        fixed = datetime(2026, 5, 26, 9, 30, tzinfo=_KST)
        clock = FixedClock(fixed)
        assert clock.now() == fixed
        assert clock.today() == fixed.date()

    def test_conforms_to_clock_protocol(self) -> None:
        assert isinstance(FixedClock(datetime(2026, 5, 26, tzinfo=_KST)), Clock)
