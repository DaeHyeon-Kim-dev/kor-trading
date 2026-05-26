from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Score:
    value: float

    def __post_init__(self) -> None:
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(f"score out of range [-1.0, 1.0]: {self.value}")
