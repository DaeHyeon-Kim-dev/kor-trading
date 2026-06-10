"""리포트 마크다운 렌더링.

PRD § 3.5 — 종목 카드 + 4관점 추천 표 + 지표 요약 + 이슈 요약.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.services.indicator_explainer import (
    explain_indicators,
    summarize_signal,
)
from kor_trading.domain.services.risk_levels import (
    STANDARD_MULTIPLIER,
    TIGHT_MULTIPLIER,
    atr_stop_loss,
)
from kor_trading.domain.values.recommendation import RecommendationLevel

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from kor_trading.application.dto.indicator_analysis import IndicatorAnalysisResult
    from kor_trading.application.dto.selection import SelectionCandidate, SelectionResult
    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
    from kor_trading.domain.entities.issue import Issue
    from kor_trading.domain.services.horizon_recommendation import HorizonRecommendation
    from kor_trading.domain.services.indicator_scorer import Horizon
    from kor_trading.domain.values.market_overview import MarketOverview


_LEVEL_LABELS: dict[RecommendationLevel, str] = {
    RecommendationLevel.STRONG_BUY: "🟢🟢 Strong Buy",
    RecommendationLevel.BUY: "🟢 Buy",
    RecommendationLevel.HOLD: "🟡 Hold/Watch",
    RecommendationLevel.SELL: "🔴 Sell",
    RecommendationLevel.STRONG_SELL: "🔴🔴 Strong Sell",
}

_HORIZON_LABELS: dict[Horizon, str] = {
    "ultra_short": "초단기",
    "short": "단기",
    "medium": "중기",
    "long": "장기",
}


def render_report_md(
    *,
    as_of: date,
    selection: SelectionResult,
    indicators: IndicatorAnalysisResult,
    horizon_recommendations: dict[str, dict[Horizon, HorizonRecommendation]],
    issues_by_ticker: Mapping[str, Sequence[Issue]] | None = None,
) -> str:
    """전체 리포트 마크다운 생성.

    horizon_recommendations: {ticker_code: {horizon: HorizonRecommendation}}
    issues_by_ticker: {ticker_code: [Issue, ...]} (옵션)
    """
    issues_map = issues_by_ticker or {}
    sections: list[str] = []
    sections.append(f"# 한국 주식 트레이딩 리포트 — {as_of.isoformat()}")
    sections.append("")
    sections.append(
        f"> 후보: {len(selection.candidates)}종목 | 전체 종목: {selection.total_screened}"
    )
    sections.append("")

    if selection.overview is not None and selection.overview.breadths:
        sections.extend(_render_overview(selection.overview))
        sections.append("")

    sections.append("## 요약 테이블")
    sections.append("| 종목 | 코드 | 등락률 | 초단기 | 단기 | 중기 | 장기 |")
    sections.append("|------|------|--------|--------|------|------|------|")
    indicator_by_ticker = {item.snapshot.ticker.code: item for item in indicators.items}
    for c in selection.candidates:
        code = c.snapshot.ticker.code
        recs = horizon_recommendations.get(code, {})
        sections.append(
            f"| {c.snapshot.ticker.name} | {code} | {c.snapshot.change_pct:+.2f}% |"
            f" {_compact_label(recs.get('ultra_short'))} |"
            f" {_compact_label(recs.get('short'))} |"
            f" {_compact_label(recs.get('medium'))} |"
            f" {_compact_label(recs.get('long'))} |"
        )
    sections.append("")

    sections.append("## 종목별 상세")
    for i, c in enumerate(selection.candidates, start=1):
        code = c.snapshot.ticker.code
        ind_item = indicator_by_ticker.get(code)
        recs = horizon_recommendations.get(code, {})
        sections.append(
            _render_card(
                i,
                c,
                ind_item.snapshot if ind_item else None,
                recs,
                issues_map.get(code, ()),
            )
        )
        sections.append("")

    if indicators.errors:
        sections.append("## 분석 실패 종목")
        for err in indicators.errors:
            sections.append(f"- {err.ticker.code} {err.ticker.name}: {err.reason}")
        sections.append("")

    return "\n".join(sections)


def render_evidence_md(
    *,
    candidate: SelectionCandidate,
    snapshot: IndicatorSnapshot | None,
    recommendations: dict[Horizon, HorizonRecommendation],
    issues: Sequence[Issue] = (),
) -> str:
    """종목별 근거 마크다운 (지표 상세 + 추천 판정 + 이슈)."""
    code = candidate.snapshot.ticker.code
    name = candidate.snapshot.ticker.name
    lines: list[str] = [
        f"# {name} ({code}) — 근거",
        "",
        f"**선정 사유**: {', '.join(candidate.selection_reasons)}",
        f"**등락률**: {candidate.snapshot.change_pct:+.2f}% "
        f"| **거래대금**: {candidate.snapshot.trading_value:,}원",
        "",
        "## 4관점 판정",
        "| 관점 | 추천 | 점수 | 근거 |",
        "|------|------|------|------|",
    ]
    for h_id in ("ultra_short", "short", "medium", "long"):
        rec = recommendations.get(h_id)
        if rec is None:
            continue
        label = _HORIZON_LABELS[h_id]
        lines.append(
            f"| {label} | {_LEVEL_LABELS[rec.level]} | {rec.score.value:+.2f} | {rec.rationale} |"
        )
    lines.append("")

    if snapshot is not None:
        lines.append("## 지표 해석")
        for line in explain_indicators(snapshot):
            lines.append(f"- {line}")
        lines.append("")
        if snapshot.atr_14 is not None:
            lines.append("## 손절 가이드")
            lines.extend(_atr_stop_lines(candidate.snapshot.close, snapshot.atr_14))
            lines.append("")
        lines.append("## 지표 상세(원시값)")
        lines.extend(_render_indicator_block(snapshot))
        lines.append("")

    if issues:
        lines.append("## 이슈 상세")
        for issue in issues:
            lines.append(f"- {_issue_line(issue)}")
            lines.append(f"  - 요약: {issue.summary} (신뢰도 {issue.confidence:.2f})")
            lines.append(f"  - 출처: {issue.source_url}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────── helpers ────────────────────────

_JO = 1_000_000_000_000  # 1조
_EOK = 100_000_000  # 1억


def _render_overview(overview: MarketOverview) -> list[str]:
    lines = ["## 시장 개요"]
    for b in overview.breadths:
        lines.append(
            f"- **{b.market}**: {b.sentiment} | "
            f"상승 {b.advancers} · 하락 {b.decliners} · 보합 {b.unchanged} "
            f"(총 {b.total}) | 평균 {b.avg_change_pct:+.2f}% | "
            f"거래대금 {_fmt_won(b.total_trading_value)}"
        )
    return lines


def _fmt_won(won: int) -> str:
    if abs(won) >= _JO:
        return f"{won / _JO:,.1f}조"
    return f"{won / _EOK:,.0f}억"


def _atr_stop_lines(close: int, atr: float) -> list[str]:
    tight = atr_stop_loss(close, atr, TIGHT_MULTIPLIER)
    standard = atr_stop_loss(close, atr, STANDARD_MULTIPLIER)
    return [
        "**손절 가이드(ATR 14)**:",
        f"- 타이트(1.5x ATR): {tight.price:,}원 ({tight.pct:+.1f}%)",
        f"- 표준(2.0x ATR): {standard.price:,}원 ({standard.pct:+.1f}%)",
    ]


def _compact_label(rec: HorizonRecommendation | None) -> str:
    if rec is None:
        return "—"
    short = {
        RecommendationLevel.STRONG_BUY: "🟢🟢",
        RecommendationLevel.BUY: "🟢",
        RecommendationLevel.HOLD: "🟡",
        RecommendationLevel.SELL: "🔴",
        RecommendationLevel.STRONG_SELL: "🔴🔴",
    }
    return short[rec.level]


def _render_card(
    index: int,
    candidate: SelectionCandidate,
    snapshot: IndicatorSnapshot | None,
    recs: dict[Horizon, HorizonRecommendation],
    issues: Sequence[Issue] = (),
) -> str:
    code = candidate.snapshot.ticker.code
    name = candidate.snapshot.ticker.name
    parts: list[str] = [
        f"### {index}. {name} ({code})",
        f"- 등락률: {candidate.snapshot.change_pct:+.2f}% "
        f"| 거래대금: {candidate.snapshot.trading_value:,}원",
        f"- 선정 사유: {', '.join(candidate.selection_reasons)}",
        "",
        "| 관점 | 추천 | 근거 |",
        "|------|------|------|",
    ]
    for h_id in ("ultra_short", "short", "medium", "long"):
        rec = recs.get(h_id)
        if rec is None:
            parts.append(f"| {_HORIZON_LABELS[h_id]} | — | — |")
        else:
            parts.append(
                f"| {_HORIZON_LABELS[h_id]} | {_LEVEL_LABELS[rec.level]} | {rec.rationale} |"
            )

    if snapshot is not None:
        parts.append("")
        parts.append(f"**지표 요약**: {summarize_signal(snapshot)}")
        parts.append("")
        parts.append("**지표 해석**:")
        for line in explain_indicators(snapshot):
            parts.append(f"- {line}")
        if snapshot.atr_14 is not None:
            parts.append("")
            parts.extend(_atr_stop_lines(candidate.snapshot.close, snapshot.atr_14))

    if issues:
        parts.append("")
        parts.append("**이슈**:")
        for issue in issues[:3]:
            parts.append(f"- {_issue_line(issue)}")
    return "\n".join(parts)


_SENTIMENT_MARK: dict[str, str] = {
    "positive": "호재",
    "negative": "악재",
    "neutral": "중립",
}


def _issue_line(issue: Issue) -> str:
    mark = _SENTIMENT_MARK.get(issue.sentiment.value, issue.sentiment.value)
    return (
        f"[{issue.source.value}, {issue.date:%m/%d}, {issue.recency_days}일 전, "
        f"{mark}/{issue.impact.value}] {issue.title}"
    )


def _render_indicator_block(snapshot: IndicatorSnapshot) -> list[str]:
    lines: list[str] = []
    if snapshot.sma_5 is not None or snapshot.sma_20 is not None:
        lines.append(
            f"- SMA: 5={_fmt(snapshot.sma_5)} / 20={_fmt(snapshot.sma_20)} "
            f"/ 60={_fmt(snapshot.sma_60)} / 120={_fmt(snapshot.sma_120)} "
            f"({snapshot.sma_alignment or '?'})"
        )
    if snapshot.macd is not None:
        lines.append(
            f"- MACD: {snapshot.macd:.2f} signal={_fmt(snapshot.macd_signal)} "
            f"hist={_fmt(snapshot.macd_hist)} "
            f"({snapshot.macd_position or '?'}, cross={snapshot.macd_cross or '?'})"
        )
    if snapshot.rsi_14 is not None:
        lines.append(f"- RSI(14): {snapshot.rsi_14:.1f}")
    if snapshot.bb_upper is not None:
        lines.append(
            f"- Bollinger: upper={_fmt(snapshot.bb_upper)} mid={_fmt(snapshot.bb_mid)} "
            f"lower={_fmt(snapshot.bb_lower)} ({snapshot.bb_position or '?'})"
        )
    if snapshot.atr_14 is not None:
        lines.append(f"- ATR(14): {snapshot.atr_14:.2f}")
    return lines


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"
