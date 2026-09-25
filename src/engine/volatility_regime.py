"""
Volatility Regime Detection Engine.

Classifies market volatility into three regimes using ATR percentile ranking
and Bollinger Band Width (BBW). Provides position-size multipliers to scale
exposure appropriately for each volatility environment.

Regime Classification (based on last 252-bar lookback):
  - LOW_VOL_COMPRESSION  : ATR percentile < 20th  → breakout imminent, size up
  - NORMAL_TRENDING      : ATR percentile 20th-70th → standard sizing
  - HIGH_VOL_SPIKE       : ATR percentile > 70th  → reduce size, widen stops
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

ATR_LOOKBACK: int = 252          # Rolling window for percentile ranking
ATR_PERIOD: int = 14             # Standard ATR period
BB_PERIOD: int = 20              # Bollinger Band period
BB_STD_MULT: float = 2.0        # Standard Bollinger Band deviation multiplier

# Percentile thresholds
LOW_VOL_THRESHOLD: float = 20.0
HIGH_VOL_THRESHOLD: float = 70.0

# Position-size multipliers per regime
SIZE_MULTIPLIER_LOW_VOL: float = 1.25
SIZE_MULTIPLIER_NORMAL: float = 1.00
SIZE_MULTIPLIER_HIGH_VOL: float = 0.60

REGIME_LOW_VOL = "LOW_VOL_COMPRESSION"
REGIME_NORMAL = "NORMAL_TRENDING"
REGIME_HIGH_VOL = "HIGH_VOL_SPIKE"


# ──────────────────────────────────────────────────────────────────────────────
# Data class
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VolatilityRegimeResult:
    """Complete volatility regime snapshot for one symbol / timeframe."""

    volatility_regime: str          # 'LOW_VOL_COMPRESSION' | 'NORMAL_TRENDING' | 'HIGH_VOL_SPIKE'
    vol_percentile: float           # ATR percentile rank in [0, 100]
    size_multiplier: float          # Recommended position-size scalar
    atr: float                      # Latest ATR value (absolute)
    bbw: Optional[float]            # Bollinger Band Width (%), or None if < 20 bars
    atr_lookback_bars: int          # Actual lookback used (may be < ATR_LOOKBACK for short series)

    def to_dict(self) -> dict:
        return {
            "volatility_regime": self.volatility_regime,
            "vol_percentile": round(self.vol_percentile, 2),
            "size_multiplier": self.size_multiplier,
            "atr": round(self.atr, 6),
            "bbw": round(self.bbw, 4) if self.bbw is not None else None,
            "atr_lookback_bars": self.atr_lookback_bars,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Core helpers
# ──────────────────────────────────────────────────────────────────────────────

def _compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = ATR_PERIOD) -> np.ndarray:
    """
    Computes Average True Range (ATR) using Wilder's smoothing.

    True Range = max(High - Low, |High - prev_Close|, |Low - prev_Close|)
    ATR[i]     = (ATR[i-1] * (period - 1) + TR[i]) / period
    """
    n = len(highs)
    if n < 2 or n < period + 1:
        return np.full(n, np.nan)

    # True Range
    tr = np.full(n, np.nan)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    # Wilder's ATR
    atr = np.full(n, np.nan)
    # Seed with simple average of first `period` TR values
    first_valid = period  # index of first ATR value
    if first_valid >= n:
        return atr
    atr[first_valid] = np.nanmean(tr[1: first_valid + 1])
    for i in range(first_valid + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def _compute_bbw(closes: np.ndarray, period: int = BB_PERIOD, std_mult: float = BB_STD_MULT) -> np.ndarray:
    """
    Computes Bollinger Band Width (BBW) as a percentage of the middle band.

    BBW = (upper - lower) / middle * 100
    where middle = SMA(close, period), upper = middle + std_mult * stdev, lower = middle - std_mult * stdev
    """
    n = len(closes)
    bbw = np.full(n, np.nan)
    if n < period:
        return bbw

    for i in range(period - 1, n):
        window = closes[i - period + 1: i + 1]
        mid = np.mean(window)
        std = np.std(window, ddof=0)
        if mid > 0:
            bbw[i] = (2.0 * std_mult * std) / mid * 100.0

    return bbw


def _atr_percentile_rank(atr_series: np.ndarray, lookback: int = ATR_LOOKBACK) -> float:
    """
    Computes the percentile rank of the latest ATR value within the last
    `lookback` valid (non-NaN) bars of the ATR series.

    Returns a value in [0.0, 100.0].
    """
    valid = atr_series[~np.isnan(atr_series)]
    if len(valid) == 0:
        return 50.0  # fallback neutral

    window = valid[-lookback:] if len(valid) >= lookback else valid
    latest = window[-1]
    # Percentile rank: fraction of values < latest
    pct = float(np.sum(window < latest)) / len(window) * 100.0
    return pct


def _classify_regime(pct: float) -> str:
    """Maps an ATR percentile to a regime string."""
    if pct < LOW_VOL_THRESHOLD:
        return REGIME_LOW_VOL
    if pct > HIGH_VOL_THRESHOLD:
        return REGIME_HIGH_VOL
    return REGIME_NORMAL


def _size_multiplier(regime: str) -> float:
    """Returns position-size multiplier for a given regime."""
    if regime == REGIME_LOW_VOL:
        return SIZE_MULTIPLIER_LOW_VOL
    if regime == REGIME_HIGH_VOL:
        return SIZE_MULTIPLIER_HIGH_VOL
    return SIZE_MULTIPLIER_NORMAL


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def classify_volatility_regime(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr_period: int = ATR_PERIOD,
    lookback: int = ATR_LOOKBACK,
) -> VolatilityRegimeResult:
    """
    Classifies the current volatility regime for a price series.

    Parameters
    ----------
    highs, lows, closes : np.ndarray
        OHLC price arrays (equal-length, chronological order).
        At minimum 2 bars are needed; 30+ bars are recommended for reliable output.
    atr_period : int
        Period for ATR computation (default 14).
    lookback : int
        Rolling percentile-rank lookback window (default 252 bars).

    Returns
    -------
    VolatilityRegimeResult
        Regime classification, percentile, size multiplier, ATR, and BBW.
    """
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)

    n = len(closes)

    # ── Edge case: very short series ──────────────────────────────────────────
    if n < 2:
        return VolatilityRegimeResult(
            volatility_regime=REGIME_NORMAL,
            vol_percentile=50.0,
            size_multiplier=SIZE_MULTIPLIER_NORMAL,
            atr=float(highs[-1] - lows[-1]) if n >= 1 else 0.0,
            bbw=None,
            atr_lookback_bars=0,
        )

    # ── ATR ───────────────────────────────────────────────────────────────────
    atr_series = _compute_atr(highs, lows, closes, period=atr_period)
    latest_atr = float(atr_series[~np.isnan(atr_series)][-1]) if np.any(~np.isnan(atr_series)) else float(highs[-1] - lows[-1])

    # ── Percentile rank ───────────────────────────────────────────────────────
    valid_atr = atr_series[~np.isnan(atr_series)]
    actual_lookback = min(len(valid_atr), lookback)
    pct = _atr_percentile_rank(atr_series, lookback=lookback)

    # ── BBW ───────────────────────────────────────────────────────────────────
    bbw_series = _compute_bbw(closes)
    valid_bbw = bbw_series[~np.isnan(bbw_series)]
    latest_bbw = float(valid_bbw[-1]) if len(valid_bbw) > 0 else None

    # ── Regime & multiplier ───────────────────────────────────────────────────
    regime = _classify_regime(pct)
    multiplier = _size_multiplier(regime)

    return VolatilityRegimeResult(
        volatility_regime=regime,
        vol_percentile=pct,
        size_multiplier=multiplier,
        atr=latest_atr,
        bbw=latest_bbw,
        atr_lookback_bars=actual_lookback,
    )
