"""백테스트 엔진 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
from kor_trading.domain.services.backtest import (
    CostModel,
    Trade,
    aggregate,
    run_backtest,
)
from kor_trading.domain.values.trade_plan import TradePlan

_BASE = date(2026, 1, 1)


def _bars(ohlc: list[tuple[int, int, int, int]]) -> list[OhlcvBar]:
    out = []
    for i, (o, h, low, c) in enumerate(ohlc):
        out.append(
            OhlcvBar(
                date=_BASE + timedelta(days=i),
                open=o,
                high=h,
                low=low,
                close=c,
                volume=1000,
                trading_value=1000,
            )
        )
    return out


_PLAN = TradePlan(
    setup="돌파",
    quality=0.7,
    entry=100,
    stop=96,
    target1=108,
    target2=112,
    risk_per_share=4,
    reward_risk=2.0,
    stop_pct=-4.0,
    rationale="r",
    invalidation="i",
)


def _fire_at(lengths: set[int]):  # type: ignore[no-untyped-def]
    def fn(bars):  # type: ignore[no-untyped-def]
        return [_PLAN] if len(bars) in lengths else []

    return fn


def _always():  # type: ignore[no-untyped-def]
    def fn(bars):  # type: ignore[no-untyped-def]
        _ = bars
        return [_PLAN]

    return fn


# ──────────────────────── run_backtest ────────────────────────
class TestRunBacktest:
    def test_no_signal_no_trades(self) -> None:
        bars = _bars([(100, 101, 99, 100)] * 6)
        assert run_backtest(bars, _fire_at(set()), warmup=2, max_hold=3) == []

    def test_win_at_target(self) -> None:
        # i=2 진입, 다음 봉(i=3) 고가 110≥108 → 승, R=(108-100)/4=2.0
        bars = _bars([(100, 101, 99, 100)] * 3 + [(100, 110, 99, 105)] + [(100, 101, 99, 100)] * 2)
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=3)
        assert len(trades) == 1
        assert trades[0].outcome == "win"
        assert trades[0].r_multiple == 2.0
        assert trades[0].exit_price == 108

    def test_loss_at_stop(self) -> None:
        bars = _bars([(100, 101, 99, 100)] * 3 + [(100, 101, 95, 97)] + [(100, 101, 99, 100)] * 2)
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=3)
        assert trades[0].outcome == "loss"
        assert trades[0].r_multiple == -1.0
        assert trades[0].exit_price == 96

    def test_stop_takes_priority_when_both_hit(self) -> None:
        # 같은 날 손절·목표 모두 도달 → 손절 우선
        bars = _bars([(100, 101, 99, 100)] * 3 + [(100, 110, 95, 100)] + [(100, 101, 99, 100)] * 2)
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=3)
        assert trades[0].outcome == "loss"

    def test_timeout_exits_at_last_close(self) -> None:
        # max_hold 내 미발생 → 마지막 종가 청산
        bars = _bars([(100, 101, 99, 100)] * 3 + [(100, 102, 98, 101), (100, 103, 98, 102)])
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=2)
        assert trades[0].outcome == "timeout"
        assert trades[0].exit_price == 102
        assert trades[0].r_multiple == 0.5  # (102-100)/4

    def test_no_overlapping_positions(self) -> None:
        # 매 호출 신호여도 청산 후에만 재진입 (1일 승 → 2칸씩 전진)
        bars = _bars([(100, 110, 99, 105)] * 8)  # 모든 다음봉이 즉시 승
        trades = run_backtest(bars, _always(), warmup=2, max_hold=3)
        # i=2,4,6 진입 → 3거래, 진입일 간격 2일
        assert len(trades) == 3
        gaps = [
            (trades[k + 1].entry_date - trades[k].entry_date).days for k in range(len(trades) - 1)
        ]
        assert gaps == [2, 2]

    def test_warmup_skips_early_bars(self) -> None:
        bars = _bars([(100, 110, 99, 105)] * 8)
        # warmup=5 → i는 5부터 시작
        trades = run_backtest(bars, _always(), warmup=5, max_hold=3)
        assert trades[0].entry_date == _BASE + timedelta(days=5)


class TestCostAndGap:
    def test_cost_reduces_r(self) -> None:
        # 목표 도달 승: 비용만큼 R 감소
        bars = _bars([(100, 101, 99, 100)] * 3 + [(100, 110, 99, 105)] + [(100, 101, 99, 100)] * 2)
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=3, cost=CostModel(0.01, 0.01))
        # fees = 100*0.01 + 108*0.01 = 2.08 → net=(108-100)-2.08=5.92 → r=1.48
        assert round(trades[0].r_multiple, 2) == 1.48

    def test_gap_down_worse_than_minus_1r(self) -> None:
        # 시가가 손절가(96) 아래 90으로 갭하락 → 90 체결, R=(90-100)/4=-2.5
        bars = _bars([(100, 101, 99, 100)] * 3 + [(90, 92, 88, 91)] + [(100, 101, 99, 100)] * 2)
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=3)
        assert trades[0].outcome == "loss"
        assert trades[0].exit_price == 90
        assert trades[0].r_multiple == -2.5

    def test_gap_up_better_than_target(self) -> None:
        # 시가가 목표(108) 위 115로 갭상승 → 115 체결, R=(115-100)/4=3.75
        bars = _bars([(100, 101, 99, 100)] * 3 + [(115, 118, 114, 116)] + [(100, 101, 99, 100)] * 2)
        trades = run_backtest(bars, _fire_at({3}), warmup=2, max_hold=3)
        assert trades[0].outcome == "win"
        assert trades[0].exit_price == 115
        assert trades[0].r_multiple == 3.75


# ──────────────────────── aggregate ────────────────────────
def _trade(setup: str, r: float, outcome: str) -> Trade:
    return Trade(
        setup=setup,
        entry_date=_BASE,
        exit_date=_BASE + timedelta(days=1),
        entry=100,
        exit_price=100 + int(r * 4),
        r_multiple=r,
        outcome=outcome,  # type: ignore[arg-type]
    )


class TestAggregate:
    def test_groups_and_sorts_by_count(self) -> None:
        trades = [
            _trade("돌파", 2.0, "win"),
            _trade("돌파", -1.0, "loss"),
            _trade("돌파", 2.0, "win"),
            _trade("눌림목", 1.0, "win"),
        ]
        stats = aggregate(trades)
        assert [s.setup for s in stats] == ["돌파", "눌림목"]  # 거래 수 내림차순
        b = stats[0]
        assert b.trades == 3
        assert round(b.win_rate, 3) == round(2 / 3, 3)
        assert round(b.expectancy_r, 3) == round((2 - 1 + 2) / 3, 3)
        assert b.avg_win_r == 2.0
        assert b.avg_loss_r == -1.0
        assert b.payoff == 2.0

    def test_payoff_zero_when_no_losses(self) -> None:
        stats = aggregate([_trade("돌파", 2.0, "win"), _trade("돌파", 1.0, "win")])
        assert stats[0].payoff == 0.0
        assert stats[0].avg_loss_r == 0.0

    def test_max_drawdown(self) -> None:
        # 누적 R: +2, +1(-1), +3(+2), -1(-4) → peak 3, 최저 -1 → MDD -4
        trades = [
            _trade("X", 2.0, "win"),
            _trade("X", -1.0, "loss"),
            _trade("X", 2.0, "win"),
            _trade("X", -4.0, "loss"),
        ]
        assert aggregate(trades)[0].max_drawdown_r == -4.0

    def test_empty(self) -> None:
        assert aggregate([]) == []
