from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from kor_trading.application.dto.selection import (
    SelectionCandidate,
    SelectionCriteria,
    SelectionResult,
)
from kor_trading.domain.ports.market_snapshot_provider import MarketSnapshotProvider
from kor_trading.domain.values.market_overview import summarize_market

if TYPE_CHECKING:
    from kor_trading.domain.entities.stock_snapshot import StockSnapshot


@dataclass
class SelectStocksUseCase:
    market_snapshots: MarketSnapshotProvider

    def execute(self, criteria: SelectionCriteria, as_of: date) -> SelectionResult:
        snapshots = self.market_snapshots.get_market_snapshots(criteria.markets, as_of)
        total_screened = len(snapshots)
        overview = summarize_market(snapshots)

        eligible = [s for s in snapshots if s.market_cap >= criteria.market_cap_min_krw]

        by_volume = sorted(eligible, key=lambda s: s.trading_value, reverse=True)
        by_change_up = sorted(eligible, key=lambda s: s.change_pct, reverse=True)
        by_change_down = sorted(eligible, key=lambda s: s.change_pct)

        top_volume = by_volume[: criteria.top_volume_n]
        top_surge = by_change_up[: criteria.surge_top_n]
        top_plunge = by_change_down[: criteria.plunge_top_n]

        rank_volume = {s.ticker.code: i + 1 for i, s in enumerate(top_volume)}
        rank_up = {s.ticker.code: i + 1 for i, s in enumerate(top_surge)}
        rank_down = {s.ticker.code: i + 1 for i, s in enumerate(top_plunge)}

        snapshots_by_code: dict[str, StockSnapshot] = {}
        for s in (*top_volume, *top_surge, *top_plunge):
            snapshots_by_code.setdefault(s.ticker.code, s)

        candidates: list[SelectionCandidate] = []
        for code, snapshot in snapshots_by_code.items():
            reasons: list[str] = []
            if code in rank_volume:
                reasons.append("top_volume")
            if code in rank_up:
                reasons.append("surge")
            if code in rank_down:
                reasons.append("plunge")
            candidates.append(
                SelectionCandidate(
                    snapshot=snapshot,
                    selection_reasons=tuple(reasons),
                    rank_by_volume=rank_volume.get(code),
                    rank_by_change_up=rank_up.get(code),
                    rank_by_change_down=rank_down.get(code),
                )
            )

        candidates.sort(
            key=lambda c: (
                c.rank_by_volume if c.rank_by_volume is not None else float("inf"),
                c.rank_by_change_up if c.rank_by_change_up is not None else float("inf"),
                c.rank_by_change_down if c.rank_by_change_down is not None else float("inf"),
            )
        )
        candidates = candidates[: criteria.max_candidates]

        return SelectionResult(
            as_of=as_of,
            total_screened=total_screened,
            candidates=tuple(candidates),
            overview=overview,
        )
