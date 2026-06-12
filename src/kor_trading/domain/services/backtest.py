"""셋업 백테스트 엔진 — 과거 일봉에서 셋업별 기대값을 측정한다.

추천 재설계 PR2: "이 셋업이 실제로 돈이 됐나"를 숫자로 검증.
순수 함수 — 일봉 리스트 + 신호함수(bars→TradePlan)를 받아 거래를 시뮬레이션.
indicator 계산은 signal_fn에 위임해 엔진은 진입/청산/집계 로직만 담는다.

청산 규칙(일봉 기준, 보수적):
- 같은 날 저가가 손절 도달 → 손절(우선 처리)
- 고가가 1차 목표 도달 → 목표 익절
- max_hold일 내 미발생 → 마지막 종가 청산(timeout)
한 종목은 동시에 1포지션만(청산 후 다음 봉부터 재진입).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import date

    from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
    from kor_trading.domain.values.trade_plan import TradePlan

Outcome = Literal["win", "loss", "timeout"]

_DEFAULT_WARMUP = 120
_DEFAULT_MAX_HOLD = 20


@dataclass(frozen=True, slots=True)
class CostModel:
    """체결가 대비 거래비용 비율(한국 주식 기본값).

    매수: 수수료 ~0.015%. 매도: 수수료 ~0.015% + 거래세 ~0.18%.
    """

    buy_rate: float = 0.00015
    sell_rate: float = 0.00195


_ZERO_COST = CostModel(buy_rate=0.0, sell_rate=0.0)


@dataclass(frozen=True, slots=True)
class Trade:
    setup: str
    entry_date: date
    exit_date: date
    entry: int
    exit_price: int
    r_multiple: float
    outcome: Outcome


@dataclass(frozen=True, slots=True)
class SetupStats:
    setup: str
    trades: int
    win_rate: float  # r>0 비율
    expectancy_r: float  # 평균 R (핵심 지표)
    avg_win_r: float
    avg_loss_r: float  # 음수
    payoff: float  # 평균이익 / |평균손실|
    max_drawdown_r: float  # 누적 R 곡선의 최대 낙폭(≤0)


def run_backtest(
    bars: Sequence[OhlcvBar],
    signal_fn: Callable[[Sequence[OhlcvBar]], list[TradePlan]],
    *,
    warmup: int = _DEFAULT_WARMUP,
    max_hold: int = _DEFAULT_MAX_HOLD,
    cost: CostModel = _ZERO_COST,
) -> list[Trade]:
    """일봉을 워크포워드하며 셋업 진입→청산을 시뮬레이션."""
    trades: list[Trade] = []
    n = len(bars)
    i = warmup
    while i < n - 1:  # 진입 다음 봉이 최소 1개 있어야 시뮬 가능
        plans = signal_fn(bars[: i + 1])
        if not plans:
            i += 1
            continue
        trade, held = _simulate(plans[0], bars[i], bars[i + 1 :], max_hold, cost)
        trades.append(trade)
        i += 1 + held  # 청산 다음 봉부터 재진입(중복 포지션 금지)
    return trades


def _simulate(
    plan: TradePlan,
    entry_bar: OhlcvBar,
    future: Sequence[OhlcvBar],
    max_hold: int,
    cost: CostModel,
) -> tuple[Trade, int]:
    horizon = future[:max_hold]
    for offset, bar in enumerate(horizon):
        ex = _exit_check(plan, bar)
        if ex is not None:
            outcome, fill = ex
            return _trade(plan, entry_bar.date, bar.date, fill, outcome, cost), offset + 1
    last = horizon[-1]
    return _trade(plan, entry_bar.date, last.date, last.close, "timeout", cost), len(horizon)


def _exit_check(plan: TradePlan, bar: OhlcvBar) -> tuple[Outcome, int] | None:
    """이 봉에서 손절/목표 도달 시 (결과, 체결가). 갭은 시가 체결. 아니면 None."""
    if bar.low <= plan.stop:  # 손절 우선(보수적). 갭하락이면 시가 체결(-1R보다 나쁨)
        return "loss", (bar.open if bar.open < plan.stop else plan.stop)
    if bar.high >= plan.target1:  # 갭상승이면 시가 체결
        return "win", (bar.open if bar.open > plan.target1 else plan.target1)
    return None


def _net_r(entry: int, exit_price: int, risk: int, cost: CostModel) -> float:
    fees = entry * cost.buy_rate + exit_price * cost.sell_rate
    return ((exit_price - entry) - fees) / risk


def _trade(
    plan: TradePlan,
    entry_date: date,
    exit_date: date,
    exit_price: int,
    outcome: Outcome,
    cost: CostModel,
) -> Trade:
    return Trade(
        setup=plan.setup,
        entry_date=entry_date,
        exit_date=exit_date,
        entry=plan.entry,
        exit_price=exit_price,
        r_multiple=_net_r(plan.entry, exit_price, plan.risk_per_share, cost),
        outcome=outcome,
    )


def aggregate(trades: Sequence[Trade]) -> list[SetupStats]:
    """셋업별 통계. 거래 수 내림차순."""
    by_setup: dict[str, list[Trade]] = {}
    for t in trades:
        by_setup.setdefault(t.setup, []).append(t)
    stats = [_stats(setup, ts) for setup, ts in by_setup.items()]
    stats.sort(key=lambda s: s.trades, reverse=True)
    return stats


def _stats(setup: str, ts: list[Trade]) -> SetupStats:
    rs = [t.r_multiple for t in ts]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return SetupStats(
        setup=setup,
        trades=len(ts),
        win_rate=len(wins) / len(ts),
        expectancy_r=sum(rs) / len(ts),
        avg_win_r=avg_win,
        avg_loss_r=avg_loss,
        payoff=(avg_win / abs(avg_loss)) if avg_loss < 0 else 0.0,
        max_drawdown_r=_max_drawdown(rs),
    )


def _max_drawdown(rs: list[float]) -> float:
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return mdd


# ──────────────────────── 페이퍼 트레이딩 채점 ────────────────────────
@dataclass(frozen=True, slots=True)
class PaperOutcome:
    status: Literal["win", "loss", "timeout", "open"]
    r_multiple: float | None  # 미청산(open)이면 None
    held_days: int | None  # 진입 다음봉부터 보유 일수, open이면 None


def score_open_position(
    plan: TradePlan,
    future: Sequence[OhlcvBar],
    *,
    max_hold: int = _DEFAULT_MAX_HOLD,
    cost: CostModel = _ZERO_COST,
) -> PaperOutcome:
    """로그된 셋업을 진입 이후 일봉(future)으로 채점.

    손절/목표 도달 → win/loss(+R), max_hold 봉 다 채움 → timeout(종가청산),
    아직 미도달이고 보유봉 < max_hold → open(미청산).
    """
    horizon = future[:max_hold]
    for offset, bar in enumerate(horizon):
        ex = _exit_check(plan, bar)
        if ex is not None:
            outcome, fill = ex
            r = _net_r(plan.entry, fill, plan.risk_per_share, cost)
            return PaperOutcome(outcome, r, offset + 1)
    if len(future) >= max_hold:  # 보유 기간 만료 → 마지막 종가 청산
        last = horizon[-1]
        return PaperOutcome(
            "timeout", _net_r(plan.entry, last.close, plan.risk_per_share, cost), max_hold
        )
    return PaperOutcome("open", None, None)
