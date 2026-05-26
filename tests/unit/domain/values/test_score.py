"""Score 값 객체 테스트.

PRD: docs/INDICATORS.md § 9 (종합 점수 -1.0 ~ +1.0)
DEVELOPMENT.md § 5.2 (Score 값 객체 예시)
"""

import dataclasses

import pytest

from kor_trading.domain.values.score import Score


class TestScoreConstruction:
    def test_accepts_value_in_range(self) -> None:
        assert Score(0.5).value == 0.5

    def test_accepts_lower_bound(self) -> None:
        assert Score(-1.0).value == -1.0

    def test_accepts_upper_bound(self) -> None:
        assert Score(1.0).value == 1.0

    def test_accepts_zero(self) -> None:
        assert Score(0.0).value == 0.0

    def test_rejects_value_above_upper_bound(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            Score(1.0001)

    def test_rejects_value_below_lower_bound(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            Score(-1.0001)


class TestScoreEquality:
    def test_equal_when_values_equal(self) -> None:
        assert Score(0.5) == Score(0.5)

    def test_not_equal_when_values_differ(self) -> None:
        assert Score(0.5) != Score(0.6)


class TestScoreImmutability:
    def test_is_frozen(self) -> None:
        score = Score(0.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            score.value = 0.7  # type: ignore[misc]
