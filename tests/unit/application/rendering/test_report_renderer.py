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
from kor_trading.domain.entities.disclosure import DisclosureSource
from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
from kor_trading.domain.entities.issue import Impact, Issue, Sentiment
from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.services.horizon_recommendation import (
    derive_horizon_recommendations,
)
from kor_trading.domain.services.indicator_scorer import compute_scores
from kor_trading.domain.values.market_overview import MarketBreadth, MarketOverview

AS_OF = date(2026, 5, 26)


def _issue(code: str, title: str) -> Issue:
    return Issue(
        ticker_code=code,
        date=AS_OF,
        title=title,
        source=DisclosureSource.DART,
        source_url="https://dart.fss.or.kr/...",
        sentiment=Sentiment.POSITIVE,
        impact=Impact.HIGH,
        confidence=0.9,
        summary="요약",
        recency_days=0,
        decay_weight=1.0,
        effective_impact=1.0,
    )


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

    def test_includes_market_overview_section(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)
        recs = derive_horizon_recommendations(compute_scores(ind_snap))
        overview = MarketOverview(
            breadths=(
                MarketBreadth(
                    market="KOSPI",
                    total=950,
                    advancers=600,
                    decliners=320,
                    unchanged=30,
                    avg_change_pct=0.42,
                    total_trading_value=8_200_000_000_000,  # 8.2조
                ),
                MarketBreadth(
                    market="KOSDAQ",
                    total=1600,
                    advancers=500,
                    decliners=1050,
                    unchanged=50,
                    avg_change_pct=-0.85,
                    total_trading_value=560_000_000_000,  # 5,600억
                ),
            )
        )
        selection = SelectionResult(
            as_of=AS_OF, total_screened=2550, candidates=(_candidate(ticker),), overview=overview
        )
        indicators = IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(IndicatorAnalysisItem(snapshot=ind_snap, scores=compute_scores(ind_snap)),),
            errors=(),
        )
        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={ticker.code: recs},
        )
        assert "## 시장 개요" in md
        assert "KOSPI" in md and "강세" in md
        assert "상승 600 · 하락 320 · 보합 30" in md
        assert "+0.42%" in md
        assert "8.2조" in md  # 조 단위 포맷
        assert "KOSDAQ" in md and "약세" in md
        assert "5,600억" in md  # 억 단위 포맷

    def test_card_includes_atr_stop_loss(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)  # close 78,500 / atr 1,850
        recs = derive_horizon_recommendations(compute_scores(ind_snap))
        selection = SelectionResult(as_of=AS_OF, total_screened=1, candidates=(_candidate(ticker),))
        indicators = IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(IndicatorAnalysisItem(snapshot=ind_snap, scores=compute_scores(ind_snap)),),
            errors=(),
        )
        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={ticker.code: recs},
        )
        assert "손절 가이드(ATR 14)" in md
        assert "74,800원" in md  # 78500 - 2*1850
        assert "75,725원" in md  # 78500 - 1.5*1850

    def test_evidence_includes_atr_stop_loss(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)
        recs = derive_horizon_recommendations(compute_scores(ind_snap))
        md = render_evidence_md(
            candidate=_candidate(ticker), snapshot=ind_snap, recommendations=recs
        )
        assert "## 손절 가이드" in md
        assert "74,800원" in md

    def test_evidence_without_atr_skips_stop_loss(self) -> None:
        ticker = _ticker()
        snap = IndicatorSnapshot(ticker=ticker, as_of=AS_OF, rsi_14=55.0)  # atr_14 None
        recs = derive_horizon_recommendations(compute_scores(snap))
        md = render_evidence_md(candidate=_candidate(ticker), snapshot=snap, recommendations=recs)
        assert "손절 가이드" not in md

    def test_includes_issue_lines_when_provided(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)
        scores = compute_scores(ind_snap)
        recs = derive_horizon_recommendations(scores)

        selection = SelectionResult(as_of=AS_OF, total_screened=1, candidates=(_candidate(ticker),))
        indicators = IndicatorAnalysisResult(
            as_of=AS_OF,
            items=(IndicatorAnalysisItem(snapshot=ind_snap, scores=scores),),
            errors=(),
        )
        issue = _issue(ticker.code, "1분기 영업이익 사상 최대")

        md = render_report_md(
            as_of=AS_OF,
            selection=selection,
            indicators=indicators,
            horizon_recommendations={ticker.code: recs},
            issues_by_ticker={ticker.code: (issue,)},
        )
        assert "이슈" in md
        assert "1분기 영업이익 사상 최대" in md
        assert "호재" in md

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

    def test_includes_issue_details_when_provided(self) -> None:
        ticker = _ticker()
        ind_snap = _indicator_snap(ticker)
        recs = derive_horizon_recommendations(compute_scores(ind_snap))
        issue = _issue(ticker.code, "공급계약 체결")

        md = render_evidence_md(
            candidate=_candidate(ticker),
            snapshot=ind_snap,
            recommendations=recs,
            issues=(issue,),
        )
        assert "이슈 상세" in md
        assert "공급계약 체결" in md
        assert "요약" in md
        assert "dart.fss.or.kr" in md

    def test_missing_snapshot_skips_indicator_block(self) -> None:
        ticker = _ticker()
        md = render_evidence_md(
            candidate=_candidate(ticker),
            snapshot=None,
            recommendations={},
        )
        assert "지표 상세" not in md
        assert "이슈 상세" not in md  # 이슈 없으면 섹션 미포함

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
