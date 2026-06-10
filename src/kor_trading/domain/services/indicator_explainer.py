"""IndicatorSnapshot → 사람이 읽는 자연어 해석.

docs/INDICATORS.md의 룰을 한국어 설명으로 변환한다.
약어(SMA bullish, RSI 51.8)를 "정배열(상승추세)", "RSI 51.8 중립" 처럼 풀어준다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot

# RSI 구간 (INDICATORS.md § 2.1)
_RSI_OVERBOUGHT = 70.0
_RSI_STRONG = 50.0
_RSI_OVERSOLD = 30.0
_MILLIONS_PER_EOK = 100  # 1억원 = 100백만원 (수급 거래대금 단위 환산)

_ALIGNMENT_KO: dict[str, str] = {
    "bullish": "정배열(단기>장기, 상승추세)",
    "bearish": "역배열(하락추세)",
    "mixed": "혼조(추세 불명확)",
}
_MACD_POSITION_KO: dict[str, str] = {
    "above_zero": "0선 위(강세권)",
    "below_zero": "0선 아래(약세권)",
}
_MACD_CROSS_KO: dict[str, str] = {
    "golden_recent": "최근 골든크로스(상승 전환 신호)",
    "dead_recent": "최근 데드크로스(하락 전환 신호)",
    "none": "교차 없음",
}
_BB_POSITION_KO: dict[str, str] = {
    "above": "밴드 상단 돌파(단기 과열 주의)",
    "upper_half": "중심선 위(강세)",
    "lower_half": "중심선 아래(약세)",
    "below": "밴드 하단 이탈(단기 과매도)",
}
_OBV_TREND_KO: dict[str, str] = {
    "up": "거래량 매집(상승 동반)",
    "down": "거래량 분산(하락 동반)",
    "flat": "거래량 중립",
}


def explain_indicators(snap: IndicatorSnapshot) -> list[str]:
    """지표별 자연어 해석 라인 목록 (데이터 없는 지표는 생략)."""
    lines: list[str] = []

    if snap.sma_alignment:
        lines.append(f"이동평균: {_ALIGNMENT_KO[snap.sma_alignment]}")

    macd_parts: list[str] = []
    if snap.macd_position:
        macd_parts.append(_MACD_POSITION_KO[snap.macd_position])
    if snap.macd_cross and snap.macd_cross != "none":
        macd_parts.append(_MACD_CROSS_KO[snap.macd_cross])
    if macd_parts:
        lines.append("MACD: " + ", ".join(macd_parts))

    lines.extend(_price_action_lines(snap))

    if snap.rsi_14 is not None:
        lines.append(f"RSI {snap.rsi_14:.1f}: {_rsi_label(snap.rsi_14)}")

    if snap.bb_position:
        bb = _BB_POSITION_KO[snap.bb_position]
        if snap.bb_squeeze:
            bb += " · 밴드 수축(변동성 확대 임박)"
        lines.append(f"볼린저밴드: {bb}")

    if snap.obv_trend:
        lines.append(f"OBV: {_OBV_TREND_KO[snap.obv_trend]}")

    if snap.foreign_net_buy_5d is not None:
        lines.append(f"외국인 5일 순매수: {_flow_label(snap.foreign_net_buy_5d)}")
    if snap.institution_net_buy_5d is not None:
        lines.append(f"기관 5일 순매수: {_flow_label(snap.institution_net_buy_5d)}")

    return lines


def summarize_signal(snap: IndicatorSnapshot) -> str:
    """카드용 한 줄 종합 해석."""
    bits: list[str] = []
    if snap.change_pct_1d is not None and snap.change_pct_1d <= -7.0:  # noqa: PLR2004
        bits.append("당일 급락")
    elif snap.change_pct_1d is not None and snap.change_pct_1d >= 8.0:  # noqa: PLR2004
        bits.append("당일 급등")
    if snap.sma_alignment == "bullish":
        bits.append("추세 강세")
    elif snap.sma_alignment == "bearish":
        bits.append("추세 약세")
    if snap.macd_cross == "golden_recent":
        bits.append("MACD 골든크로스")
    elif snap.macd_cross == "dead_recent":
        bits.append("MACD 데드크로스")
    if snap.rsi_14 is not None:
        bits.append(f"RSI {snap.rsi_14:.0f} {_rsi_label(snap.rsi_14)}")
    if snap.obv_trend == "up":
        bits.append("거래량 매집")
    elif snap.obv_trend == "down":
        bits.append("거래량 분산")
    return " · ".join(bits) if bits else "데이터 부족"


# ──────────────────────── helpers ────────────────────────


_VOLUME_SPIKE_DISPLAY = 1.5


def _price_action_lines(snap: IndicatorSnapshot) -> list[str]:
    out: list[str] = []
    if snap.change_pct_1d is not None:
        out.append(f"당일 등락: {snap.change_pct_1d:+.2f}% {_intraday_label(snap.change_pct_1d)}")
    if snap.return_5d is not None:
        out.append(f"5일 수익률: {snap.return_5d:+.2f}%")
    if snap.volume_spike is not None and snap.volume_spike >= _VOLUME_SPIKE_DISPLAY:
        out.append(f"거래량: 20일 평균의 {snap.volume_spike:.1f}배 (급증)")
    return out


def _intraday_label(change_pct: float) -> str:
    if change_pct <= -7.0:  # noqa: PLR2004
        return "(급락 — 스윙 진입 보류)"
    if change_pct <= -3.0:  # noqa: PLR2004
        return "(하락)"
    if change_pct >= 8.0:  # noqa: PLR2004
        return "(급등 — 단기 과열 주의)"
    if change_pct >= 3.0:  # noqa: PLR2004
        return "(상승)"
    return "(보합)"


def _rsi_label(rsi: float) -> str:
    if rsi >= _RSI_OVERBOUGHT:
        return "과매수(조정 가능)"
    if rsi >= _RSI_STRONG:
        return "중립~강세"
    if rsi >= _RSI_OVERSOLD:
        return "중립~약세"
    return "과매도(반등 가능)"


def _flow_label(amount: int) -> str:
    # amount는 백만원 단위(KIS *_ntby_tr_pbmn). 1억원 = 100백만원.
    eok = amount / _MILLIONS_PER_EOK
    if amount > 0:
        return f"순매수 +{eok:,.0f}억(매수 우위)"
    if amount < 0:
        return f"순매도 {eok:,.0f}억(매도 우위)"
    return "중립"
