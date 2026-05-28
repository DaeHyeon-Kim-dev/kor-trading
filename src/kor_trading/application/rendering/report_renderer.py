"""리포트 마크다운 렌더링.

PRD § 3.5 — 종목 카드 + 4관점 추천 표 + 지표 요약 + 이슈 요약.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.values.recommendation import RecommendationLevel

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.application.dto.indicator_analysis import IndicatorAnalysisResult
    from kor_trading.application.dto.selection import SelectionCandidate, SelectionResult
    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot
    from kor_trading.domain.services.horizon_recommendation import HorizonRecommendation
    from kor_trading.domain.services.indicator_scorer import Horizon


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
) -> str:
    """전체 리포트 마크다운 생성.

    horizon_recommendations: {ticker_code: {horizon: HorizonRecommendation}}
    """
    sections: list[str] = []
    sections.append(f"# 한국 주식 트레이딩 리포트 — {as_of.isoformat()}")
    sections.append("")
    sections.append(
        f"> 후보: {len(selection.candidates)}종목 | 전체 종목: {selection.total_screened}"
    )
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
        sections.append(_render_card(i, c, ind_item.snapshot if ind_item else None, recs))
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
) -> str:
    """종목별 근거 마크다운 (지표 상세 + 추천 판정)."""
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
        "| 관점 | 추천 | 점수 |",
        "|------|------|------|",
    ]
    for h_id in ("ultra_short", "short", "medium", "long"):
        rec = recommendations.get(h_id)
        if rec is None:
            continue
        label = _HORIZON_LABELS[h_id]
        lines.append(f"| {label} | {_LEVEL_LABELS[rec.level]} | {rec.score.value:+.2f} |")
    lines.append("")

    if snapshot is not None:
        lines.append("## 지표 상세")
        lines.extend(_render_indicator_block(snapshot))
        lines.append("")

    return "\n".join(lines)


# ──────────────────────── helpers ────────────────────────


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
) -> str:
    code = candidate.snapshot.ticker.code
    name = candidate.snapshot.ticker.name
    parts: list[str] = [
        f"### {index}. {name} ({code})",
        f"- 등락률: {candidate.snapshot.change_pct:+.2f}% "
        f"| 거래대금: {candidate.snapshot.trading_value:,}원",
        f"- 선정 사유: {', '.join(candidate.selection_reasons)}",
        "",
        "| 관점 | 추천 |",
        "|------|------|",
    ]
    for h_id in ("ultra_short", "short", "medium", "long"):
        rec = recs.get(h_id)
        if rec is None:
            parts.append(f"| {_HORIZON_LABELS[h_id]} | — |")
        else:
            parts.append(f"| {_HORIZON_LABELS[h_id]} | {_LEVEL_LABELS[rec.level]} |")

    if snapshot is not None:
        parts.append("")
        parts.append(f"**지표 요약**: {_short_indicator_summary(snapshot)}")
    return "\n".join(parts)


def _short_indicator_summary(snapshot: IndicatorSnapshot) -> str:
    pieces: list[str] = []
    if snapshot.sma_alignment:
        pieces.append(f"SMA {snapshot.sma_alignment}")
    if snapshot.macd_position:
        pieces.append(f"MACD {snapshot.macd_position}")
    if snapshot.rsi_14 is not None:
        pieces.append(f"RSI {snapshot.rsi_14:.1f}")
    if snapshot.bb_position:
        pieces.append(f"BB {snapshot.bb_position}")
    return ", ".join(pieces) if pieces else "데이터 부족"


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
