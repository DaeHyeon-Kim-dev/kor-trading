"""시장 개요 값 객체 — 선정 universe로부터 계산한 시장 폭(breadth).

PRD R2 — 리포트 최상단 시장 분위기 섹션.
종목별 등락률을 집계해 상승/하락/보합 종목 수, 평균 등락률, 거래대금을 담는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kor_trading.domain.entities.ticker import Market  # noqa: TC001 (런타임 그룹핑 키)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kor_trading.domain.entities.stock_snapshot import StockSnapshot

# 상승 우위/하락 우위를 판정하는 종목 수 배수 (이 배수 미만이면 혼조)
_DOMINANCE_RATIO = 1.5


@dataclass(frozen=True, slots=True)
class MarketBreadth:
    """단일 시장(KOSPI/KOSDAQ)의 폭 집계."""

    market: Market
    total: int
    advancers: int
    decliners: int
    unchanged: int
    avg_change_pct: float
    total_trading_value: int

    @property
    def sentiment(self) -> str:
        """상승/하락 종목 수 비율로 본 시장 분위기."""
        if self.advancers >= self.decliners * _DOMINANCE_RATIO:
            return "강세"
        if self.decliners >= self.advancers * _DOMINANCE_RATIO:
            return "약세"
        return "혼조"


@dataclass(frozen=True, slots=True)
class MarketOverview:
    """시장별 폭 집계 모음."""

    breadths: tuple[MarketBreadth, ...]


def overall_regime(overview: MarketOverview) -> str:
    """전 시장 합산 폭으로 본 레짐(강세/약세/혼조). 빈 경우 혼조."""
    up = sum(b.advancers for b in overview.breadths)
    down = sum(b.decliners for b in overview.breadths)
    if up == 0 and down == 0:
        return "혼조"
    if up >= down * _DOMINANCE_RATIO:
        return "강세"
    if down >= up * _DOMINANCE_RATIO:
        return "약세"
    return "혼조"


def summarize_market(snapshots: Sequence[StockSnapshot]) -> MarketOverview:
    """전체 universe 스냅샷에서 시장별 폭을 계산.

    시장이 처음 등장한 순서를 유지한다(보통 KOSPI→KOSDAQ).
    """
    buckets: dict[Market, list[StockSnapshot]] = {}
    for s in snapshots:
        buckets.setdefault(s.ticker.market, []).append(s)

    breadths = [_breadth(market, items) for market, items in buckets.items()]
    return MarketOverview(breadths=tuple(breadths))


def _breadth(market: Market, items: list[StockSnapshot]) -> MarketBreadth:
    advancers = sum(1 for s in items if s.change_pct > 0)
    decliners = sum(1 for s in items if s.change_pct < 0)
    return MarketBreadth(
        market=market,
        total=len(items),
        advancers=advancers,
        decliners=decliners,
        unchanged=len(items) - advancers - decliners,
        avg_change_pct=sum(s.change_pct for s in items) / len(items),
        total_trading_value=sum(s.trading_value for s in items),
    )
