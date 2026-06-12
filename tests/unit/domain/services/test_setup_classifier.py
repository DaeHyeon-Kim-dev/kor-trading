"""셋업 분류기 테스트 — 각 셋업 매칭/비매칭/경계."""

from __future__ import annotations

from datetime import date
from typing import Any

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.setup_classifier import classify_setups

AS_OF = date(2026, 6, 11)
_T = Ticker(code="005930", name="X", market="KOSPI")


def _snap(**kw: Any) -> IndicatorSnapshot:
    return IndicatorSnapshot(ticker=_T, as_of=AS_OF, **kw)


# ──────────────────────── 가드 ────────────────────────
class TestGuards:
    def test_no_atr_no_setups(self) -> None:
        assert classify_setups(_snap(rsi_14=25.0), close=10_000) == []

    def test_zero_atr_no_setups(self) -> None:
        assert classify_setups(_snap(atr_14=0.0, rsi_14=25.0), close=10_000) == []

    def test_zero_close_no_setups(self) -> None:
        assert classify_setups(_snap(atr_14=100.0), close=0) == []

    def test_no_match_returns_empty(self) -> None:
        snap = _snap(atr_14=200.0, sma_alignment="bearish", rsi_14=65.0, sma_20=9000.0)
        assert classify_setups(snap, close=9_500) == []


# ──────────────────────── 추세 눌림목 ────────────────────────
class TestPullback:
    def _match(self, **kw: Any) -> IndicatorSnapshot:
        base: dict[str, Any] = dict(
            atr_14=200.0,
            sma_alignment="bullish",
            sma_5=10_000.0,
            sma_20=9_800.0,
            rsi_14=50.0,
            change_pct_1d=-1.0,
        )
        base.update(kw)
        return _snap(**base)

    def test_matches_and_builds_plan(self) -> None:
        plans = classify_setups(self._match(), close=9_900)
        p = next(x for x in plans if x.setup == "추세 눌림목")
        assert p.entry == 9_900
        assert p.risk_per_share == 400  # 2.0 * 200
        assert p.stop == 9_500
        assert p.target1 == 9_900 + 800  # 2R
        assert p.reward_risk == 2.0

    def test_flow_and_macd_raise_quality(self) -> None:
        plain = classify_setups(self._match(), close=9_900)[0].quality
        boosted = classify_setups(
            self._match(
                foreign_net_buy_5d=100,
                institution_net_buy_5d=50,
                macd_position="above_zero",
            ),
            close=9_900,
        )
        q = next(x for x in boosted if x.setup == "추세 눌림목").quality
        assert q > plain
        assert q <= 1.0

    def test_only_foreign_buy_bonus(self) -> None:
        plans = classify_setups(self._match(foreign_net_buy_5d=100), close=9_900)
        assert any(p.setup == "추세 눌림목" for p in plans)

    def test_not_bullish_skips(self) -> None:
        plans = classify_setups(self._match(sma_alignment="mixed"), close=9_900)
        assert all(p.setup != "추세 눌림목" for p in plans)

    def test_rsi_out_of_band_skips(self) -> None:
        plans = classify_setups(self._match(rsi_14=70.0), close=9_900)
        assert all(p.setup != "추세 눌림목" for p in plans)

    def test_far_from_ma_skips(self) -> None:
        # close가 sma_5보다 한참 위 → near_5 실패
        plans = classify_setups(self._match(), close=10_500)
        assert all(p.setup != "추세 눌림목" for p in plans)

    def test_crash_day_skips(self) -> None:
        plans = classify_setups(self._match(change_pct_1d=-5.0), close=9_900)
        assert all(p.setup != "추세 눌림목" for p in plans)

    def test_missing_sma_skips(self) -> None:
        plans = classify_setups(self._match(sma_5=None), close=9_900)
        assert all(p.setup != "추세 눌림목" for p in plans)

    def test_missing_rsi_skips(self) -> None:
        # 정배열·이동평균은 있으나 RSI 없음 → 눌림목 판정 불가
        plans = classify_setups(self._match(rsi_14=None), close=9_900)
        assert all(p.setup != "추세 눌림목" for p in plans)


# ──────────────────────── 돌파 ────────────────────────
class TestBreakout:
    def _match(self, **kw: Any) -> IndicatorSnapshot:
        base: dict[str, Any] = dict(
            atr_14=200.0,
            volume_spike=3.0,
            change_pct_1d=5.0,
            sma_20=9_000.0,
            macd_position="above_zero",
        )
        base.update(kw)
        return _snap(**base)

    def test_matches(self) -> None:
        p = next(x for x in classify_setups(self._match(), close=9_500) if x.setup == "돌파")
        assert p.reward_risk == 2.5
        assert "3.0x" in p.rationale

    def test_quality_caps(self) -> None:
        p = next(
            x
            for x in classify_setups(self._match(volume_spike=10.0), close=9_500)
            if x.setup == "돌파"
        )
        assert p.quality <= 1.0

    def test_low_volume_skips(self) -> None:
        plans = classify_setups(self._match(volume_spike=1.2), close=9_500)
        assert all(p.setup != "돌파" for p in plans)

    def test_overheated_change_skips(self) -> None:
        plans = classify_setups(self._match(change_pct_1d=20.0), close=9_500)
        assert all(p.setup != "돌파" for p in plans)

    def test_below_ma_skips(self) -> None:
        plans = classify_setups(self._match(sma_20=10_000.0), close=9_500)
        assert all(p.setup != "돌파" for p in plans)

    def test_alignment_path_without_macd(self) -> None:
        # macd_position 없이 sma_alignment로 above 충족
        p = classify_setups(self._match(macd_position=None, sma_alignment="bullish"), close=9_500)
        assert any(x.setup == "돌파" for x in p)


# ──────────────────────── 수급 주도 ────────────────────────
class TestFlowLed:
    def _match(self, **kw: Any) -> IndicatorSnapshot:
        base: dict[str, Any] = dict(
            atr_14=200.0,
            foreign_net_buy_5d=100,
            institution_net_buy_5d=50,
            sma_20=9_000.0,
            sma_alignment="bullish",
        )
        base.update(kw)
        return _snap(**base)

    def test_matches(self) -> None:
        p = next(x for x in classify_setups(self._match(), close=9_100) if x.setup == "수급 주도")
        assert p.reward_risk == 3.0
        assert p.risk_per_share == 500  # 2.5 * 200

    def test_mixed_alignment_lower_quality(self) -> None:
        bull = next(
            x for x in classify_setups(self._match(), close=9_100) if x.setup == "수급 주도"
        )
        mixed = next(
            x
            for x in classify_setups(self._match(sma_alignment="mixed"), close=9_100)
            if x.setup == "수급 주도"
        )
        assert mixed.quality < bull.quality

    def test_one_side_selling_skips(self) -> None:
        plans = classify_setups(self._match(institution_net_buy_5d=-50), close=9_100)
        assert all(p.setup != "수급 주도" for p in plans)

    def test_weak_price_skips(self) -> None:
        plans = classify_setups(self._match(), close=8_000)  # 20일선 한참 아래
        assert all(p.setup != "수급 주도" for p in plans)

    def test_missing_flow_skips(self) -> None:
        plans = classify_setups(self._match(foreign_net_buy_5d=None), close=9_100)
        assert all(p.setup != "수급 주도" for p in plans)


# ──────────────────────── 과매도 반등 ────────────────────────
class TestBounce:
    def _match(self, **kw: Any) -> IndicatorSnapshot:
        base: dict[str, Any] = dict(
            atr_14=200.0, rsi_14=28.0, bb_position="lower_half", change_pct_1d=1.5
        )
        base.update(kw)
        return _snap(**base)

    def test_matches(self) -> None:
        p = next(x for x in classify_setups(self._match(), close=5_000) if x.setup == "과매도 반등")
        assert p.reward_risk == 1.0
        assert p.risk_per_share == 300  # 1.5 * 200

    def test_not_oversold_skips(self) -> None:
        plans = classify_setups(self._match(rsi_14=45.0), close=5_000)
        assert all(p.setup != "과매도 반등" for p in plans)

    def test_not_at_lower_skips(self) -> None:
        plans = classify_setups(self._match(bb_position="upper_half"), close=5_000)
        assert all(p.setup != "과매도 반등" for p in plans)

    def test_not_turning_skips(self) -> None:
        plans = classify_setups(self._match(change_pct_1d=-0.5), close=5_000)
        assert all(p.setup != "과매도 반등" for p in plans)

    def test_risk_exceeds_close_excluded(self) -> None:
        # close 100, atr 80 → bounce risk=120 ≥ close → 제외
        snap = self._match(atr_14=80.0)
        plans = classify_setups(snap, close=100)
        assert all(p.setup != "과매도 반등" for p in plans)


# ──────────────────────── 다중 매칭 정렬 ────────────────────────
def test_multiple_setups_sorted_by_quality() -> None:
    # 눌림목(정배열+되돌림+수급+macd) & 수급주도 동시 충족
    snap = _snap(
        atr_14=200.0,
        sma_alignment="bullish",
        sma_5=10_000.0,
        sma_20=9_800.0,
        rsi_14=50.0,
        change_pct_1d=-1.0,
        macd_position="above_zero",
        foreign_net_buy_5d=100,
        institution_net_buy_5d=50,
    )
    plans = classify_setups(snap, close=9_900)
    names = {p.setup for p in plans}
    assert {"추세 눌림목", "수급 주도"} <= names
    # 품질 내림차순
    assert plans == sorted(plans, key=lambda p: p.quality, reverse=True)
