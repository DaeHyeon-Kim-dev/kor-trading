"""일봉 시계열로부터 기술적 지표를 계산.

순수 함수 — 외부 I/O 없음. pandas만 사용.
계산 결과는 IndicatorSnapshot의 raw 값(sma_*, macd, rsi_14 등).
신호 분류(alignment, cross, position)는 후속 PR의 분류 서비스에서 채움.

PRD: docs/INDICATORS.md § 1~4
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from kor_trading.domain.entities.indicator_snapshot import IndicatorSnapshot

if TYPE_CHECKING:
    from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
    from kor_trading.domain.entities.ticker import Ticker


_SMA_PERIODS = (5, 20, 60, 120)
_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9
_RSI_PERIOD = 14
_BBANDS_PERIOD = 20
_BBANDS_STD = 2.0
_ATR_PERIOD = 14
_STOCH_K = 14
_STOCH_D = 3


def calculate_indicators(ticker: Ticker, bars: list[OhlcvBar]) -> IndicatorSnapshot:
    """일봉 리스트(가장 오래된 → 최신 정렬)를 받아 IndicatorSnapshot 반환."""
    if not bars:
        return IndicatorSnapshot(ticker=ticker, as_of=date.today())

    df = _to_dataframe(bars)
    last_date = bars[-1].date

    sma_values = {p: _sma(df["close"], p) for p in _SMA_PERIODS}
    macd_val, signal_val, hist_val = _macd(df["close"])
    rsi = _rsi(df["close"], _RSI_PERIOD)
    bb_upper, bb_mid, bb_lower = _bollinger(df["close"], _BBANDS_PERIOD, _BBANDS_STD)
    atr = _atr(df, _ATR_PERIOD)
    stoch_k, stoch_d = _stochastic(df, _STOCH_K, _STOCH_D)

    return IndicatorSnapshot(
        ticker=ticker,
        as_of=last_date,
        sma_5=sma_values[5],
        sma_20=sma_values[20],
        sma_60=sma_values[60],
        sma_120=sma_values[120],
        macd=macd_val,
        macd_signal=signal_val,
        macd_hist=hist_val,
        rsi_14=rsi,
        stoch_k=stoch_k,
        stoch_d=stoch_d,
        bb_upper=bb_upper,
        bb_mid=bb_mid,
        bb_lower=bb_lower,
        atr_14=atr,
    )


# ────────────────────────── helpers ──────────────────────────


def _to_dataframe(bars: list[OhlcvBar]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )


def _sma(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    return float(close.rolling(period).mean().iloc[-1])


def _ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def _macd(close: pd.Series) -> tuple[float | None, float | None, float | None]:
    needed = _MACD_SLOW + _MACD_SIGNAL
    if len(close) < needed:
        return None, None, None
    fast_ema = _ema(close, _MACD_FAST)
    slow_ema = _ema(close, _MACD_SLOW)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=_MACD_SIGNAL, adjust=False).mean()
    hist = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1])


def _rsi(close: pd.Series, period: int) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_gain = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    value = rsi_series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _bollinger(
    close: pd.Series, period: int, std_multiplier: float
) -> tuple[float | None, float | None, float | None]:
    if len(close) < period:
        return None, None, None
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_multiplier * std
    lower = mid - std_multiplier * std
    return float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1])


def _atr(df: pd.DataFrame, period: int) -> float | None:
    if len(df) < period + 1:
        return None
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1
    )
    value = tr.rolling(period).mean().iloc[-1]
    if pd.isna(value):  # pragma: no cover (defensive — unreachable with >= period+1 bars)
        return None
    return float(value)


def _stochastic(
    df: pd.DataFrame, k_period: int, d_period: int
) -> tuple[float | None, float | None]:
    if len(df) < k_period + d_period:
        return None, None
    high_n = df["high"].rolling(k_period).max()
    low_n = df["low"].rolling(k_period).min()
    range_n = high_n - low_n
    # 변동성 0 (모든 가격 동일) → NaN
    range_n_safe = range_n.where(range_n != 0)
    k = 100 * (df["close"] - low_n) / range_n_safe
    d = k.rolling(d_period).mean()
    k_val = k.iloc[-1]
    d_val = d.iloc[-1]
    if pd.isna(k_val) or pd.isna(d_val):
        return None, None
    return float(k_val), float(d_val)
