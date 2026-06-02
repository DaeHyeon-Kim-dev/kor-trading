"""RunPipelineUseCase — 종목 선정 → 지표·이슈 분석 → 리포트 생성 전체 흐름."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.application.dto.selection import SelectionCriteria
    from kor_trading.application.use_cases.analyze_indicators import (
        AnalyzeIndicatorsUseCase,
    )
    from kor_trading.application.use_cases.analyze_issues import AnalyzeIssuesUseCase
    from kor_trading.application.use_cases.generate_report import (
        GeneratedReport,
        GenerateReportUseCase,
    )
    from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase


log = structlog.get_logger()


@dataclass
class RunPipelineUseCase:
    select_stocks: SelectStocksUseCase
    analyze_indicators: AnalyzeIndicatorsUseCase
    generate_report: GenerateReportUseCase
    analyze_issues: AnalyzeIssuesUseCase | None = None

    def execute(self, *, criteria: SelectionCriteria, as_of: date, run_id: str) -> GeneratedReport:
        log.info("pipeline.start", run_id=run_id, as_of=as_of.isoformat())

        selection = self.select_stocks.execute(criteria, as_of)
        log.info(
            "pipeline.selection",
            run_id=run_id,
            total_screened=selection.total_screened,
            candidates=len(selection.candidates),
        )

        tickers = [c.snapshot.ticker for c in selection.candidates]
        indicators = self.analyze_indicators.execute(tickers, as_of)
        log.info(
            "pipeline.indicators",
            run_id=run_id,
            ok=len(indicators.items),
            errors=len(indicators.errors),
        )

        issue_scores: dict[str, float] = {}
        if self.analyze_issues is not None:
            issue_result = self.analyze_issues.execute(tickers, as_of)
            issue_scores = {item.ticker_code: item.overall_score for item in issue_result.items}
            log.info("pipeline.issues", run_id=run_id, analyzed=len(issue_result.items))

        report = self.generate_report.execute(
            run_id=run_id,
            as_of=as_of,
            selection=selection,
            indicators=indicators,
            issue_scores_by_ticker=issue_scores,
        )
        log.info("pipeline.done", run_id=run_id, report_path=str(report.report_path))
        return report
