"""GenerateReportUseCase — 분석 결과를 리포트로 합쳐 저장+전송."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from kor_trading.application.rendering.report_renderer import (
    render_evidence_md,
    render_report_md,
)
from kor_trading.domain.services.horizon_recommendation import (
    derive_horizon_recommendations,
)

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from kor_trading.application.dto.indicator_analysis import (
        IndicatorAnalysisResult,
    )
    from kor_trading.application.dto.selection import SelectionResult
    from kor_trading.domain.ports.notifier import Notifier
    from kor_trading.domain.ports.report_repository import ReportRepository


log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class GeneratedReport:
    run_id: str
    report_path: Path
    evidence_paths: tuple[Path, ...]


@dataclass
class GenerateReportUseCase:
    repository: ReportRepository
    notifier: Notifier

    def execute(
        self,
        *,
        run_id: str,
        as_of: date,
        selection: SelectionResult,
        indicators: IndicatorAnalysisResult,
        issue_scores_by_ticker: dict[str, float] | None = None,
    ) -> GeneratedReport:
        issue_scores = issue_scores_by_ticker or {}
        indicator_items = {item.snapshot.ticker.code: item for item in indicators.items}

        horizon_recs: dict[str, dict] = {}  # type: ignore[type-arg]
        for c in selection.candidates:
            code = c.snapshot.ticker.code
            ind_item = indicator_items.get(code)
            if ind_item is None:
                continue
            issue_score = issue_scores.get(code, 0.0)
            horizon_recs[code] = derive_horizon_recommendations(
                ind_item.scores, issue_score=issue_score
            )

        report_md = render_report_md(
            as_of=as_of,
            selection=selection,
            indicators=indicators,
            horizon_recommendations=horizon_recs,
        )
        report_path = self.repository.save_report(run_id, report_md)

        evidence_paths: list[Path] = []
        for c in selection.candidates:
            code = c.snapshot.ticker.code
            ind_item = indicator_items.get(code)
            evidence_md = render_evidence_md(
                candidate=c,
                snapshot=ind_item.snapshot if ind_item else None,
                recommendations=horizon_recs.get(code, {}),
            )
            evidence_paths.append(self.repository.save_evidence(run_id, code, evidence_md))

        self._notify(report_md, report_path)

        return GeneratedReport(
            run_id=run_id,
            report_path=report_path,
            evidence_paths=tuple(evidence_paths),
        )

    def _notify(self, report_md: str, report_path: Path) -> None:
        # 1) 헤더(첫 줄) + 요약을 메시지로
        header = report_md.split("\n\n", maxsplit=1)[0] if report_md else "(empty)"
        try:
            self.notifier.send_message(header)
            self.notifier.send_document(
                filename=report_path.name,
                content=report_md.encode("utf-8"),
                caption="full report",
            )
        except Exception as e:  # 전송 실패가 전체를 막지 않도록
            log.error("report.notify_failed", error=str(e))
