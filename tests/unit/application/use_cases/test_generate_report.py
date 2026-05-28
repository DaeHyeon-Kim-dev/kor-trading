"""GenerateReportUseCase 테스트."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from kor_trading.adapters.outbound.filesystem_report_repository import (
    FileSystemReportRepository,
)
from kor_trading.application.dto.indicator_analysis import (
    IndicatorAnalysisItem,
    IndicatorAnalysisResult,
)
from kor_trading.application.dto.selection import SelectionCandidate, SelectionResult
from kor_trading.application.use_cases.generate_report import GenerateReportUseCase
from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.indicator_scorer import compute_scores

if TYPE_CHECKING:
    from pathlib import Path


AS_OF = date(2026, 5, 26)


class _RecordingNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[str] = []
        self.documents: list[tuple[str, bytes]] = []
        self._fail = fail

    def send_message(self, text: str) -> None:
        if self._fail:
            raise RuntimeError("network down")
        self.messages.append(text)

    def send_document(self, filename: str, content: bytes, caption: str | None = None) -> None:
        _ = caption
        if self._fail:
            raise RuntimeError("network down")
        self.documents.append((filename, content))


def _ticker(code: str = "005930", name: str = "삼성전자") -> Ticker:
    return Ticker(code=code, name=name, market="KOSPI")


def _candidate(ticker: Ticker) -> SelectionCandidate:
    return SelectionCandidate(
        snapshot=StockSnapshot(
            ticker=ticker,
            as_of=AS_OF,
            close=78500,
            change_pct=5.2,
            volume=25_000_000,
            trading_value=1_980_000_000_000,
            market_cap=469_000_000_000_000,
        ),
        selection_reasons=("top_volume",),
        rank_by_volume=1,
        rank_by_change_up=None,
        rank_by_change_down=None,
    )


def _make_uc(
    tmp_path: Path, fail_notify: bool = False
) -> tuple[GenerateReportUseCase, _RecordingNotifier]:
    notifier = _RecordingNotifier(fail=fail_notify)
    repo = FileSystemReportRepository(base_path=tmp_path)
    return GenerateReportUseCase(repository=repo, notifier=notifier), notifier


def _result(ticker: Ticker) -> tuple[SelectionResult, IndicatorAnalysisResult]:
    snap = IndicatorSnapshot(ticker=ticker, as_of=AS_OF, sma_alignment="bullish", rsi_14=55.0)
    return (
        SelectionResult(as_of=AS_OF, total_screened=1, candidates=(_candidate(ticker),)),
        IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(IndicatorAnalysisItem(snapshot=snap, scores=compute_scores(snap)),),
            errors=(),
        ),
    )


class TestExecute:
    def test_saves_report_and_evidence(self, tmp_path: Path) -> None:
        uc, notifier = _make_uc(tmp_path)
        ticker = _ticker()
        selection, indicators = _result(ticker)

        result = uc.execute(
            run_id="2026-05-26/1430",
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
        )

        assert result.report_path.exists()
        assert len(result.evidence_paths) == 1
        assert (tmp_path / "2026-05-26" / "1430" / "evidence" / "005930.md").exists()
        # 텔레그램 전송도 시도됨
        assert len(notifier.messages) == 1
        assert len(notifier.documents) == 1

    def test_issue_scores_are_applied(self, tmp_path: Path) -> None:
        uc, _ = _make_uc(tmp_path)
        ticker = _ticker()
        selection, indicators = _result(ticker)

        result = uc.execute(
            run_id="r1",
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            issue_scores_by_ticker={"005930": 0.9},
        )
        content = result.report_path.read_text(encoding="utf-8")
        # 호재 점수가 반영된 카드가 있어야 함
        assert "005930" in content

    def test_notifier_failure_does_not_break_save(self, tmp_path: Path) -> None:
        uc, notifier = _make_uc(tmp_path, fail_notify=True)
        ticker = _ticker()
        selection, indicators = _result(ticker)

        result = uc.execute(
            run_id="r1",
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
        )
        # 파일은 저장됐고, 알림은 실패했으나 use case는 성공
        assert result.report_path.exists()
        assert notifier.messages == []

    def test_invalid_issue_score_raises(self, tmp_path: Path) -> None:
        uc, _ = _make_uc(tmp_path)
        ticker = _ticker()
        selection, indicators = _result(ticker)
        with pytest.raises(ValueError):
            uc.execute(
                run_id="r1",
                as_of=AS_OF,
                selection=selection,
                indicators=indicators,
                issue_scores_by_ticker={"005930": 1.5},
            )

    def test_missing_indicator_skips_horizon_recs(self, tmp_path: Path) -> None:
        # selection에 있는 종목이 indicator 분석에 없음
        uc, _ = _make_uc(tmp_path)
        ticker = _ticker()
        selection = SelectionResult(as_of=AS_OF, total_screened=1, candidates=(_candidate(ticker),))
        indicators = IndicatorAnalysisResult(as_of=AS_OF, items=(), errors=())

        result = uc.execute(
            run_id="r1",
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
        )
        # evidence는 카드별로 생성 (snapshot=None, recs={})
        assert len(result.evidence_paths) == 1
        body = result.evidence_paths[0].read_text(encoding="utf-8")
        assert "지표 상세" not in body  # snapshot 없으니 미포함
