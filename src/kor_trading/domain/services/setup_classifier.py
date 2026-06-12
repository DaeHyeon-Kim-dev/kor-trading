"""셋업 분류기 — IndicatorSnapshot + 현재가에서 매매 셋업을 판정한다.

연속 점수 추천의 한계(가중평균이 전부 중앙으로 수렴 → 전부 Hold)를 벗어나,
구체적 셋업에 매칭되면 R-멀티플 매매플랜을 낸다. 매칭 없으면 빈 리스트(=관망).

셋업(스윙):
- 추세 눌림목: 정배열 + 20일선 되돌림 + RSI 리셋
- 돌파: 거래량 급증 동반 강세 돌파
- 수급 주도: 외국인·기관 동반 순매수 + 가격 견조
- 과매도 반등(역추세, 주의): RSI<32 + 볼린저 하단 + 당일 반등

손절은 셋업별 ATR 배수, 목표는 손익비(R) 배수. 상수는 상단에서 조정.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.values.trade_plan import TradePlan

if TYPE_CHECKING:
    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot

# ──────────────────────── 튜닝 상수 ────────────────────────
# (셋업별) 손절 ATR 배수 / 1차 목표 손익비 R
_PULLBACK_STOP_MULT, _PULLBACK_R = 2.0, 2.0
_BREAKOUT_STOP_MULT, _BREAKOUT_R = 2.0, 2.5
_FLOW_STOP_MULT, _FLOW_R = 2.5, 3.0
_BOUNCE_STOP_MULT, _BOUNCE_R = 1.5, 1.0

_RSI_PULLBACK_LO, _RSI_PULLBACK_HI = 40.0, 58.0
_RSI_OVERSOLD = 32.0
_VOLUME_BREAKOUT = 2.0
_BREAKOUT_CHG_LO, _BREAKOUT_CHG_HI = 3.0, 15.0  # 강하되 과열(추격) 아님
_NOT_CRASH_CHG = -3.5
# ATR 손절폭이 현재가의 이 비율(%)을 넘으면 스윙 셋업으로 부적합(과변동성) → 제외
_MAX_STOP_PCT = 12.0

_Detection = tuple[float, str, str]  # (quality, rationale, invalidation)


def classify_setups(snap: IndicatorSnapshot, close: int) -> list[TradePlan]:
    """매칭되는 셋업의 매매플랜을 품질 내림차순으로 반환. 없으면 []."""
    if close <= 0 or snap.atr_14 is None or snap.atr_14 <= 0:
        return []

    plans: list[TradePlan] = []
    for name, stop_mult, target_r, detector in _SETUPS:
        det = detector(snap, close)
        if det is None:
            continue
        plan = _build_plan(name, det, close, snap.atr_14, stop_mult, target_r)
        if plan is not None:
            plans.append(plan)
    plans.sort(key=lambda p: p.quality, reverse=True)
    return plans


def _build_plan(
    name: str, det: _Detection, close: int, atr: float, stop_mult: float, target_r: float
) -> TradePlan | None:
    quality, rationale, invalidation = det
    risk = max(1, round(stop_mult * atr))
    if risk >= close:  # 손절가가 0 이하가 되는 비정상(초저가) 종목은 제외
        return None
    if risk / close * 100 > _MAX_STOP_PCT:  # 손절폭이 과도하게 넓음(고변동성) → 부적합
        return None
    stop = close - risk
    return TradePlan(
        setup=name,
        quality=min(1.0, quality),
        entry=close,
        stop=stop,
        target1=close + round(target_r * risk),
        target2=close + round((target_r + 1.0) * risk),
        risk_per_share=risk,
        reward_risk=target_r,
        stop_pct=(stop - close) / close * 100,
        rationale=rationale,
        invalidation=invalidation,
    )


# ──────────────────────── 셋업 디텍터 ────────────────────────
def _flow_bonus(snap: IndicatorSnapshot) -> float:
    f5, i5 = snap.foreign_net_buy_5d, snap.institution_net_buy_5d
    bonus = 0.0
    if f5 is not None and f5 > 0:
        bonus += 0.1
    if i5 is not None and i5 > 0:
        bonus += 0.1
    return bonus


def _detect_pullback(snap: IndicatorSnapshot, close: int) -> _Detection | None:
    if snap.sma_alignment != "bullish" or snap.sma_5 is None or snap.sma_20 is None:
        return None
    if snap.rsi_14 is None:
        return None
    near_5 = close <= snap.sma_5 * 1.005
    near_20 = snap.sma_20 * 0.98 <= close <= snap.sma_20 * 1.05
    rsi_ok = _RSI_PULLBACK_LO <= snap.rsi_14 <= _RSI_PULLBACK_HI
    not_crash = snap.change_pct_1d is None or snap.change_pct_1d > _NOT_CRASH_CHG
    if not (near_5 and near_20 and rsi_ok and not_crash):
        return None
    quality = 0.6 + _flow_bonus(snap)
    if snap.macd_position == "above_zero":
        quality += 0.1
    return (
        quality,
        "정배열 상승추세에서 20일선 부근 되돌림 + RSI 리셋(과매수 해소)",
        "종가 기준 20일선 명확히 이탈 시 셋업 무효",
    )


def _detect_breakout(snap: IndicatorSnapshot, close: int) -> _Detection | None:
    if snap.volume_spike is None or snap.change_pct_1d is None or snap.sma_20 is None:
        return None
    vol_ok = snap.volume_spike >= _VOLUME_BREAKOUT
    above = close > snap.sma_20 and (
        snap.macd_position == "above_zero" or snap.sma_alignment in ("bullish", "mixed")
    )
    chg_ok = _BREAKOUT_CHG_LO <= snap.change_pct_1d <= _BREAKOUT_CHG_HI
    if not (vol_ok and above and chg_ok):
        return None
    quality = min(1.0, 0.6 + min(0.3, (snap.volume_spike - _VOLUME_BREAKOUT) * 0.1))
    return (
        quality,
        f"거래량 급증({snap.volume_spike:.1f}x) 동반 강세 돌파, 추세 위 위치",
        "돌파 캔들 저점(또는 손절가) 이탈 시 무효",
    )


def _detect_flow_led(snap: IndicatorSnapshot, close: int) -> _Detection | None:
    f5, i5 = snap.foreign_net_buy_5d, snap.institution_net_buy_5d
    if f5 is None or i5 is None or snap.sma_20 is None:
        return None
    both_buy = f5 > 0 and i5 > 0
    firm = close >= snap.sma_20 * 0.99 and snap.sma_alignment in ("bullish", "mixed")
    if not (both_buy and firm):
        return None
    quality = 0.65
    if snap.sma_alignment == "bullish":
        quality += 0.1
    return (
        quality,
        "외국인·기관 5일 동반 순매수 + 가격 견조(추세 초입 가능)",
        "수급 동반 이탈 또는 20일선 이탈 시 무효",
    )


def _detect_bounce(snap: IndicatorSnapshot, _close: int) -> _Detection | None:
    if snap.rsi_14 is None or snap.change_pct_1d is None:
        return None
    oversold = snap.rsi_14 < _RSI_OVERSOLD
    at_lower = snap.bb_position in ("below", "lower_half")
    turning = snap.change_pct_1d > 0
    if not (oversold and at_lower and turning):
        return None
    return (
        0.4,  # 역추세 — 보수적 품질
        "과매도(RSI<32) + 볼린저 하단 + 당일 반등 시작(역추세, 타이트 손절)",
        "당일 저점 이탈 시 즉시 손절",
    )


_SETUPS = (
    ("돌파", _BREAKOUT_STOP_MULT, _BREAKOUT_R, _detect_breakout),
    ("수급 주도", _FLOW_STOP_MULT, _FLOW_R, _detect_flow_led),
    ("추세 눌림목", _PULLBACK_STOP_MULT, _PULLBACK_R, _detect_pullback),
    ("과매도 반등", _BOUNCE_STOP_MULT, _BOUNCE_R, _detect_bounce),
)
