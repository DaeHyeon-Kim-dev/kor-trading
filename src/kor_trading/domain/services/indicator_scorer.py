"""IndicatorSnapshot → 카테고리/종합/4관점 점수 산출.

PRD: docs/INDICATORS.md § 6 (신호 조합 가이드), § 9 (종합 점수).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from kor_trading.domain.values.score import Score

if TYPE_CHECKING:
    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot


Category = Literal["trend", "momentum", "volatility", "volume", "flow"]
Horizon = Literal["ultra_short", "short", "medium", "long"]

_RSI_EXTREME_HIGH = 80
_RSI_HIGH = 70
_RSI_NEUTRAL = 50
_RSI_LOW = 30

# 당일 등락률 구간 (스윙 매매 모멘텀)
_PLUNGE_PCT = -7.0
_DROP_PCT = -3.0
_RISE_PCT = 3.0
_SURGE_PCT = 8.0
_VOLUME_SPIKE_THRESHOLD = 2.0


# INDICATORS.md § 9 기본 가중치
_DEFAULT_WEIGHTS: dict[Category, float] = {
    "trend": 0.25,
    "momentum": 0.20,
    "volatility": 0.10,
    "volume": 0.15,
    "flow": 0.30,
}

# 시점별 가중치 (스윙 매매 최적화 — 관점별 우선 지표를 뚜렷이 차등)
# momentum은 당일 등락률·5일 수익률을 포함하므로 단기 관점에서 비중 ↑
_HORIZON_WEIGHTS: dict[Horizon, dict[Category, float]] = {
    # 초단기(당일~3일): 당일 모멘텀·거래량 급증이 결정적
    "ultra_short": {
        "trend": 0.10,
        "momentum": 0.40,
        "volatility": 0.10,
        "volume": 0.25,
        "flow": 0.15,
    },
    # 단기(1주~1개월, 스윙 핵심): 모멘텀 + 추세 균형
    "short": {
        "trend": 0.30,
        "momentum": 0.30,
        "volatility": 0.10,
        "volume": 0.15,
        "flow": 0.15,
    },
    # 중기(1~3개월): 추세 위주, 모멘텀 보조
    "medium": {
        "trend": 0.45,
        "momentum": 0.15,
        "volatility": 0.05,
        "volume": 0.10,
        "flow": 0.25,
    },
    # 장기(3개월+): 추세 중심 (재무·산업은 본 도메인 범위 외)
    "long": {
        "trend": 0.55,
        "momentum": 0.10,
        "volatility": 0.05,
        "volume": 0.05,
        "flow": 0.25,
    },
}


@dataclass(frozen=True, slots=True)
class IndicatorScores:
    category: dict[Category, Score]
    overall: Score
    by_horizon: dict[Horizon, Score]


def compute_scores(
    snap: IndicatorSnapshot, weights: dict[Category, float] | None = None
) -> IndicatorScores:
    """IndicatorSnapshot → IndicatorScores.

    데이터가 없는 카테고리(예: 수급 미제공)는 가중치에서 제외하고 재정규화한다.
    그렇지 않으면 죽은 카테고리(가중치 0.30의 flow)가 전체 점수를 희석한다.
    """
    base_w = weights if weights is not None else _DEFAULT_WEIGHTS
    cat: dict[Category, Score] = {
        "trend": Score(_trend_score(snap)),
        "momentum": Score(_momentum_score(snap)),
        "volatility": Score(_volatility_score(snap)),
        "volume": Score(_volume_score(snap)),
        "flow": Score(_flow_score(snap)),
    }
    available = _available_categories(snap)
    overall = Score(_weighted_sum(cat, _effective_weights(base_w, available)))
    horizons: tuple[Horizon, ...] = ("ultra_short", "short", "medium", "long")
    by_horizon: dict[Horizon, Score] = {
        h: Score(_weighted_sum(cat, _effective_weights(_HORIZON_WEIGHTS[h], available)))
        for h in horizons
    }
    return IndicatorScores(category=cat, overall=overall, by_horizon=by_horizon)


def _available_categories(snap: IndicatorSnapshot) -> set[Category]:
    """데이터가 있는 카테고리만. flow는 수급 데이터 있을 때만 포함."""
    available: set[Category] = {"trend", "momentum", "volatility", "volume"}
    if any(
        v is not None
        for v in (
            snap.foreign_net_buy_5d,
            snap.foreign_net_buy_20d,
            snap.institution_net_buy_5d,
            snap.institution_net_buy_20d,
        )
    ):
        available.add("flow")
    return available


def _effective_weights(
    base: dict[Category, float], available: set[Category]
) -> dict[Category, float]:
    """available 카테고리만 남기고 가중치 합이 1이 되도록 재정규화."""
    kept = {c: w for c, w in base.items() if c in available}
    total = sum(kept.values())
    if total <= 0:  # pragma: no cover (방어)
        return kept
    return {c: w / total for c, w in kept.items()}


# ──────────────────────── category scorers ────────────────────────


def _trend_score(snap: IndicatorSnapshot) -> float:
    score = 0.0
    if snap.sma_alignment == "bullish":
        score += 0.5
    elif snap.sma_alignment == "bearish":
        score -= 0.5
    if snap.macd_position == "above_zero":
        score += 0.3
    elif snap.macd_position == "below_zero":
        score -= 0.3
    if snap.macd_cross == "golden_recent":
        score += 0.2
    elif snap.macd_cross == "dead_recent":
        score -= 0.2
    return _clip(score)


def _momentum_score(snap: IndicatorSnapshot) -> float:
    """RSI + 5일 수익률 + 당일 등락률을 평균 (스윙 매매 모멘텀)."""
    components: list[float] = []
    if snap.rsi_14 is not None:
        components.append(_rsi_component(snap.rsi_14))
    if snap.return_5d is not None:
        # 5일 +15% → +1.0, -15% → -1.0
        components.append(_clip(snap.return_5d / 15.0))
    if snap.change_pct_1d is not None:
        components.append(_intraday_component(snap.change_pct_1d))
    if not components:
        return 0.0
    return _clip(sum(components) / len(components))


def _rsi_component(rsi: float) -> float:
    if rsi >= _RSI_EXTREME_HIGH:
        return -0.4  # 과매수 → 조정 위험
    if rsi >= _RSI_HIGH:
        return 0.2
    if rsi >= _RSI_NEUTRAL:
        return 0.3  # 중립~강세 (기존 0.5 → 0.3 하향)
    if rsi >= _RSI_LOW:
        return -0.3
    return 0.2  # 과매도 → 반등 여지


def _intraday_component(change_pct: float) -> float:
    """당일 등락률 → 모멘텀 기여. 급락은 강한 음(스윙 진입 부적절)."""
    if change_pct <= _PLUNGE_PCT:  # -7% 이하 급락
        return -0.7
    if change_pct <= _DROP_PCT:  # -3% ~ -7%
        return -0.3
    if change_pct >= _SURGE_PCT:  # +8% 이상 급등 → 단기 과열
        return -0.1
    if change_pct >= _RISE_PCT:  # +3% ~ +8%
        return 0.3
    return 0.0


def _volatility_score(snap: IndicatorSnapshot) -> float:
    if snap.bb_squeeze and snap.bb_position in ("upper_half", "above"):
        return 0.5
    if snap.bb_position == "above":
        return -0.3
    if snap.bb_position == "below":
        return 0.3
    return 0.0


def _volume_score(snap: IndicatorSnapshot) -> float:
    score = 0.0
    if snap.obv_trend == "up":
        score += 0.4
    elif snap.obv_trend == "down":
        score -= 0.4
    if snap.volume_spike is not None and snap.volume_spike >= _VOLUME_SPIKE_THRESHOLD:
        score += 0.3  # 거래량 급증 = 관심 집중
    return _clip(score)


def _flow_score(snap: IndicatorSnapshot) -> float:
    """외국인 + 기관 누적 매수세."""
    score = 0.0
    if snap.foreign_net_buy_5d is not None:
        if snap.foreign_net_buy_5d > 0:
            score += 0.4
        elif snap.foreign_net_buy_5d < 0:
            score -= 0.4
    if snap.institution_net_buy_5d is not None:
        if snap.institution_net_buy_5d > 0:
            score += 0.3
        elif snap.institution_net_buy_5d < 0:
            score -= 0.3
    return _clip(score)


# ──────────────────────── helpers ────────────────────────


def _weighted_sum(cat: dict[Category, Score], w: dict[Category, float]) -> float:
    # w(유효 가중치)에 있는 카테고리만 합산
    return _clip(sum(cat[c].value * weight for c, weight in w.items()))


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))
