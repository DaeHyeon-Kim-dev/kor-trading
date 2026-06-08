"""IndicatorSnapshot 엔티티 — 종목 1개의 한 시점 지표 결과 보관.

평탄한 dataclass로 모든 지표를 nullable 필드로 보관 (데이터 부족한 종목 대응).
계산 로직과 분리 — 본 모듈은 데이터 컨테이너만.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import date

    from kor_trading.domain.entities.ticker import Ticker


_RSI_MIN = 0.0
_RSI_MAX = 100.0

SmaAlignment = Literal["bullish", "bearish", "mixed"]
MacdCross = Literal["golden_recent", "dead_recent", "none"]
MacdPosition = Literal["above_zero", "below_zero"]
BollingerPosition = Literal["above", "upper_half", "lower_half", "below"]
ObvTrend = Literal["up", "down", "flat"]
VwapPosition = Literal["above", "below"]


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    ticker: Ticker
    as_of: date

    # 추세 — 이동평균
    sma_5: float | None = None
    sma_20: float | None = None
    sma_60: float | None = None
    sma_120: float | None = None
    sma_alignment: SmaAlignment | None = None

    # 추세 — MACD
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    macd_cross: MacdCross | None = None
    macd_position: MacdPosition | None = None

    # 모멘텀
    rsi_14: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None

    # 단기 가격 액션 (스윙 매매용)
    change_pct_1d: float | None = None  # 당일 등락률 (%)
    return_5d: float | None = None  # 최근 5거래일 수익률 (%)
    volume_spike: float | None = None  # 당일 거래량 / 20일 평균 (배수)

    # 변동성 — 볼린저
    bb_upper: float | None = None
    bb_mid: float | None = None
    bb_lower: float | None = None
    bb_position: BollingerPosition | None = None
    bb_squeeze: bool | None = None
    atr_14: float | None = None

    # 거래량
    obv_trend: ObvTrend | None = None
    vwap_position: VwapPosition | None = None

    # 수급 (한국 특화)
    foreign_net_buy_5d: int | None = None
    foreign_net_buy_20d: int | None = None
    institution_net_buy_5d: int | None = None
    institution_net_buy_20d: int | None = None
    short_balance_ratio: float | None = None

    def __post_init__(self) -> None:
        zero_to_100 = (
            ("rsi_14", self.rsi_14),
            ("stoch_k", self.stoch_k),
            ("stoch_d", self.stoch_d),
        )
        for name, value in zero_to_100:
            if value is not None and not _RSI_MIN <= value <= _RSI_MAX:
                raise ValueError(f"{name} out of range [{_RSI_MIN},{_RSI_MAX}]: {value}")
        if self.short_balance_ratio is not None and self.short_balance_ratio < 0:
            raise ValueError(f"short_balance_ratio non-negative: {self.short_balance_ratio}")
        if (
            self.bb_upper is not None
            and self.bb_lower is not None
            and self.bb_upper < self.bb_lower
        ):
            raise ValueError(f"bb_upper ({self.bb_upper}) must be >= bb_lower ({self.bb_lower})")
