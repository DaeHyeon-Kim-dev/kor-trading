"""마크다운 렌더링 테스트."""

from __future__ import annotations

from datetime import date

from kor_trading.application.dto.indicator_analysis import (
    IndicatorAnalysisError,
    IndicatorAnalysisItem,
    IndicatorAnalysisResult,
)
from kor_trading.application.dto.selection import (
    SelectionCandidate,
    SelectionResult,
)
from kor_trading.application.rendering.report_renderer import (
    render_evidence_md,
    render_report_md,
)
from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.horizon_recommendation import (
    derive_horizon_recommendations,
)
from kor_trading.domain.services.indicator_scorer import compute_scores

AS_OF = date(2026, 5, 26)


def _ticker(code: str = "005930", name: str = "삼성전자") -> Ticker:
    return Ticker(code=code, name=name, market="KOSPI")


def _stock_snap(ticker: Ticker) -> StockSnapshot:
    return StockSnapshot(
        ticker=ticker,
        as_of=AS_OF,
        close=78500,
        change_pct=5.2,
        volume=25_000_000,
        trading_value=1_980_000_000_000,
        market_cap=469_000_000_000_000,
    )


def _candidate(ticker: Ticker) -> SelectionCandidate:
    return SelectionCandidate(
        snapshot=_stock_snap(ticker),
        selection_reasons=("top_volume", "surge"),
        rank_by_volume=1,
        rank_by_change_up=7,
        rank_by_change_down=None,
    )


def _indicator_snap(ticker: Ticker) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        ticker=ticker,
        as_of=AS_OF,
        sma_5=77800,
        sma_20=75200,
        sma_60=72100,
        sma_120=70500,
        sma_alignment="bullish",
        macd=1.2,
        macd_signal=0.8,
        macd_hist=0.4,
        macd_cross="golden_recent",
        macd_position="above_zero",
        rsi_14=62.3,
        bb_upper=80100,
        bb_mid=75200,
        bb_lower=70300,
        bb_position="upper_half",
        atr_14=1850.0,
    )


class TestRenderReport:
    def test_includes_header_and_summary_table(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)
        scores = compute_scores(ind_snap)
        recs = derive_horizon_recommendations(scores, issue_score=0.0)

        selection = SelectionResult(
            as_of=AS_OF, total_screened=2350, candidates=(_candidate(ticker),)
        )
        indicators = IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(IndicatorAnalysisItem(snapshot=ind_snap, scores=scores),),
            errors=(),
        )

        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={ticker.code: recs},
        )

        assert "# 한국 주식 트레이딩 리포트" in md
        assert "삼성전자" in md
        assert "005930" in md
        assert "## 요약 테이블" in md
        assert "## 종목별 상세" in md

    def test_renders_empty_when_no_candidates(self) -> None:
        selection = SelectionResult(as_of=AS_OF, total_screened=0, candidates=())
        indicators = IndicatorAnalysisResult(as_of=AS_OF, items=(), errors=())
        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={},
        )
        assert "후보: 0종목" in md

    def test_no_horizon_recommendations_shows_dash(self) -> None:
        # candidate가 indicators에 없는 경우 (분석 실패한 종목 포함)
        ticker = _ticker("000888", "test")
        selection = SelectionResult(as_of=AS_OF, total_screened=1, candidates=(_candidate(ticker),))
        indicators = IndicatorAnalysisResult(as_of=AS_OF, items=(), errors=())
        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={},
        )
        # 카드의 추천 표에 '—' 또는 요약 테이블에 빈 마크가 있어야 함
        assert "—" in md

    def test_includes_failure_section_when_errors(self) -> None:
        ticker = _ticker("000999", "장애주")
        selection = SelectionResult(as_of=AS_OF, total_screened=1, candidates=())
        indicators = IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(),
            errors=(IndicatorAnalysisError(ticker=ticker, reason="network"),),
        )
        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={},
        )
        assert "분석 실패 종목" in md
        assert "000999" in md


class TestRenderEvidence:
    def test_includes_4_horizons_and_indicator_details(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)
        recs = derive_horizon_recommendations(compute_scores(ind_snap))

        md = render_evidence_md(
            candidate=_candidate(ticker),
            snapshot=ind_snap,
            recommendations=recs,
        )

        assert "근거" in md
        assert "4관점 판정" in md
        assert "초단기" in md
        assert "단기" in md
        assert "중기" in md
        assert "장기" in md
        assert "지표 상세" in md
        assert "MACD" in md
        assert "RSI" in md

    def test_missing_snapshot_skips_indicator_block(self) -> None:
        ticker = _ticker()
        md = render_evidence_md(
            candidate=_candidate(ticker),
            snapshot=None,
            recommendations={},
        )
        assert "지표 상세" not in md

    def test_partial_snapshot_renders_what_available(self) -> None:
        ticker = _ticker()
        partial = IndicatorSnapshot(ticker=ticker, as_of=AS_OF, rsi_14=55.0)
        md = render_evidence_md(
            candidate=_candidate(ticker),
            snapshot=partial,
            recommendations={},
        )
        assert "RSI" in md
        assert "MACD" not in md  # MACD 데이터 없으면 라인 없음

    def test_snapshot_without_rsi_skips_rsi_line(self) -> None:
        ticker = _ticker()
        snap = IndicatorSnapshot(ticker=ticker, as_of=AS_OF, sma_5=100.0)
        md = render_evidence_md(
            candidate=_candidate(ticker),
            snapshot=snap,
            recommendations={},
        )
        assert "RSI" not in md

    def test_empty_snapshot_summary_says_data_missing(self) -> None:
        ticker = _ticker()
        scores = compute_scores(IndicatorSnapshot(ticker=ticker, as_of=AS_OF))
        recs = derive_horizon_recommendations(scores)

        selection = SelectionResult(as_of=AS_OF, total_screened=1, candidates=(_candidate(ticker),))
        indicators = IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(
                IndicatorAnalysisItem(
                    snapshot=IndicatorSnapshot(ticker=ticker, as_of=AS_OF), scores=scores
                ),
            ),
            errors=(),
        )
        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={ticker.code: recs},
        )
        assert "데이터 부족" in md
