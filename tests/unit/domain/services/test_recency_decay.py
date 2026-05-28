"""RecencyDecaySchedule + days_between 테스트."""

from datetime import date

import pytest

from kor_trading.domain.services.recency_decay import RecencyDecaySchedule, days_between


class TestWeightFor:
    def test_today_is_full_weight(self) -> None:
        assert RecencyDecaySchedule().weight_for(0) == 1.00

    def test_one_to_two_days(self) -> None:
        s = RecencyDecaySchedule()
        assert s.weight_for(1) == 0.85
        assert s.weight_for(2) == 0.85

    def test_three_to_seven_days(self) -> None:
        s = RecencyDecaySchedule()
        assert s.weight_for(3) == 0.60
        assert s.weight_for(7) == 0.60

    def test_eight_to_fourteen_days(self) -> None:
        s = RecencyDecaySchedule()
        assert s.weight_for(8) == 0.30
        assert s.weight_for(14) == 0.30

    def test_fifteen_plus_days(self) -> None:
        s = RecencyDecaySchedule()
        assert s.weight_for(15) == 0.10
        assert s.weight_for(60) == 0.10

    def test_negative_recency_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            RecencyDecaySchedule().weight_for(-1)

    def test_custom_schedule(self) -> None:
        s = RecencyDecaySchedule(today=2.0, days_1_to_2=1.5)
        assert s.weight_for(0) == 2.0
        assert s.weight_for(1) == 1.5


class TestDaysBetween:
    def test_same_day(self) -> None:
        d = date(2026, 5, 26)
        assert days_between(d, d) == 0

    def test_one_day_diff(self) -> None:
        assert days_between(date(2026, 5, 25), date(2026, 5, 26)) == 1

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="after"):
            days_between(date(2026, 5, 27), date(2026, 5, 26))
