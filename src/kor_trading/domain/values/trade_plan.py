"""매매 플랜 값 객체 — 셋업 1건의 진입/손절/목표/손익비/리스크.

PRD 추천 재설계: 연속 점수 대신 '셋업(setup)'에 매칭되면 구체적 매매 플랜을 낸다.
모든 가격은 원(int), 손익비(reward_risk)는 손절폭 대비 1차 목표 배수(R).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TradePlan:
    """한 셋업의 실행 플랜."""

    setup: str  # 셋업 이름 (예: "추세 눌림목")
    quality: float  # 0~1, 셋업 강도(정렬·신뢰도용)
    entry: int  # 진입 기준가 (현재가)
    stop: int  # 손절가
    target1: int  # 1차 목표 (= entry + R*risk)
    target2: int  # 2차 목표 (러너)
    risk_per_share: int  # 1주당 리스크 (entry - stop, 원)
    reward_risk: float  # 손익비 (1차 목표 기준 R)
    stop_pct: float  # 손절가의 현재가 대비 (%) — 음수
    rationale: str  # 진입 근거
    invalidation: str  # 무효화(셋업 깨짐) 조건

    def __post_init__(self) -> None:
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError(f"quality out of range [0,1]: {self.quality}")
        if self.stop >= self.entry:
            raise ValueError(f"stop({self.stop}) must be below entry({self.entry})")


def suggested_shares(account_krw: int, risk_pct: float, risk_per_share: int) -> int:
    """계좌리스크 기반 매수 수량. account*risk_pct ÷ 1주당 리스크 (내림)."""
    if risk_per_share <= 0:
        return 0
    budget = account_krw * (risk_pct / 100.0)
    return int(budget // risk_per_share)
