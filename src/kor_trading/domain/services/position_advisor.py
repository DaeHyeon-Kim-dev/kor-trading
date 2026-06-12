"""보유 포지션 관리 — 평단 대비 손익 + 추세 상태로 매매 타이밍을 제안한다.

사용 패턴 3: "xxx 보유중, 평단 xxx원, 지금 어떻게?" 에 답한다.
신규 진입(setup_classifier)과 달리 '이미 들고 있는' 관점:
보유/추가매수/일부 익절/전량 익절/손절 중 하나를 근거·손절선과 함께 제시.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kor_trading.domain.services.setup_classifier import classify_setups

if TYPE_CHECKING:
    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot

_OVEREXTENDED_RSI = 75.0
_TREND_BREAK_MA_RATIO = 0.97  # 20일선 대비 이 비율 아래면 추세 이탈
_STOP_MA_RATIO = 0.97  # 추세 손절선 = 20일선 * 이 비율
_ATR_TRAIL_MULT = 2.0


@dataclass(frozen=True, slots=True)
class PositionAdvice:
    pnl_pct: float  # 평단 대비 손익 (%)
    action: str  # 추가매수 검토 / 보유 / 일부 익절 / 전량 익절 / 손절
    reason: str
    stop_level: int  # 권장 손절가 (0이면 산출 불가)
    note: str  # 레벨 안내


def manage_position(snap: IndicatorSnapshot, close: int, avg_cost: int) -> PositionAdvice:
    if avg_cost <= 0:
        raise ValueError(f"avg_cost must be positive: {avg_cost}")

    pnl = (close - avg_cost) / avg_cost * 100
    in_profit = close >= avg_cost
    stop = _stop_level(snap, close)

    if _trend_broken(snap, close):
        action, reason = (
            ("전량 익절", "추세 이탈(정배열 붕괴/20일선 하향 이탈) — 수익 보호 청산")
            if in_profit
            else ("손절", "추세 이탈 + 손실 구간 — 원칙대로 손절")
        )
    elif _overextended(snap) and in_profit:
        action = "일부 익절"
        reason = "단기 과열(RSI 과매수/밴드 상단) — 일부 차익실현 후 잔량 보유"
    elif _has_pullback(snap, close):
        action = "추가매수 검토"
        reason = "상승추세 눌림목 — 분할 추가매수 가능 구간"
    else:
        action = "보유"
        reason = "추세 유지 — 손절선 지키며 보유"

    return PositionAdvice(
        pnl_pct=pnl,
        action=action,
        reason=reason,
        stop_level=stop,
        note=_level_note(snap, close, stop),
    )


def _trend_broken(snap: IndicatorSnapshot, close: int) -> bool:
    if snap.sma_alignment == "bearish":
        return True
    return snap.sma_20 is not None and close < snap.sma_20 * _TREND_BREAK_MA_RATIO


def _overextended(snap: IndicatorSnapshot) -> bool:
    if snap.rsi_14 is not None and snap.rsi_14 >= _OVEREXTENDED_RSI:
        return True
    return snap.bb_position == "above"


def _has_pullback(snap: IndicatorSnapshot, close: int) -> bool:
    return any(p.setup == "추세 눌림목" for p in classify_setups(snap, close))


def _stop_level(snap: IndicatorSnapshot, close: int) -> int:
    if snap.sma_20 is not None:
        lvl = round(snap.sma_20 * _STOP_MA_RATIO)
        if lvl < close:
            return lvl
    if snap.atr_14 is not None:
        lvl = round(close - _ATR_TRAIL_MULT * snap.atr_14)
        if 0 < lvl < close:
            return lvl
    return 0


def _level_note(snap: IndicatorSnapshot, close: int, stop: int) -> str:
    parts: list[str] = []
    if stop > 0:
        parts.append(f"권장 손절선 ≈ {stop:,}원({(stop - close) / close * 100:+.1f}%)")
    if snap.sma_20 is not None:
        parts.append(f"20일선 {round(snap.sma_20):,}원")
    return " · ".join(parts) if parts else "기준 레벨 산출 불가(데이터 부족)"
