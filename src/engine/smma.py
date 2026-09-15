"""
Larsson Line (CTO Line) Mathematical Engine.
Implements exact Smoothed Moving Average (SMMA / Wilder's MA) and
ribbon state classification matching TradingView PineScript implementation.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class LarssonState(str, Enum):
    GOLD = "GOLD"        # Orange / Bullish
    BLUE = "BLUE"        # Navy / Bearish
    NEUTRAL = "NEUTRAL"  # Silver / Transition or Mixed


# Ribbon periods
PERIOD_V1 = 15
PERIOD_M1 = 19
PERIOD_M2 = 25
PERIOD_V2 = 29
MIN_WARMUP_CANDLES = 150  # Needed for SMMA exponential decay stabilization


def compute_hl2(high: np.ndarray, low: np.ndarray) -> np.ndarray:
    """Computes median price (High + Low) / 2."""
    return (high + low) / 2.0


def compute_smma(src: np.ndarray, length: int) -> np.ndarray:
    """
    Computes Wilder's Smoothed Moving Average (SMMA).
    Matches TradingView PineScript:
    smma := na(smma[1]) ? sma(src, length) : (smma[1] * (length - 1) + src) / length
    """
    n = len(src)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < length:
        return out

    # First valid value is SMA of the first 'length' bars
    out[length - 1] = np.mean(src[:length])

    # Recurrent SMMA calculation
    factor = length - 1
    for i in range(length, n):
        out[i] = (out[i - 1] * factor + src[i]) / length

    return out


def evaluate_larsson_state(v1: float, m1: float, m2: float, v2: float) -> LarssonState:
    """
    Evaluates the Larsson Line ribbon state given the 4 SMMA values:
    v1: SMMA(hl2, 15)
    m1: SMMA(hl2, 19)
    m2: SMMA(hl2, 25)
    v2: SMMA(hl2, 29)

    PineScript logic:
    p2 = v1<m1 != v1<v2 or m2<v2 != v1<v2
    p3 = not p2 and v1<v2
    p1 = not p2 and not p3
    c = p1 ? color.orange : p2 ? color.silver : color.navy
    """
    if any(np.isnan([v1, m1, m2, v2])):
        return LarssonState.NEUTRAL

    b_v1_m1 = v1 < m1
    b_v1_v2 = v1 < v2
    b_m2_v2 = m2 < v2

    p2 = (b_v1_m1 != b_v1_v2) or (b_m2_v2 != b_v1_v2)
    p3 = (not p2) and b_v1_v2
    p1 = (not p2) and (not p3)

    if p1:
        return LarssonState.GOLD
    elif p3:
        return LarssonState.BLUE
    else:
        return LarssonState.NEUTRAL


def compute_larsson_series(high: np.ndarray, low: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[LarssonState]]:
    """
    Computes all 4 SMMA series and the full list of historical states for a given set of candles.
    """
    hl2 = compute_hl2(high, low)
    v1 = compute_smma(hl2, PERIOD_V1)
    m1 = compute_smma(hl2, PERIOD_M1)
    m2 = compute_smma(hl2, PERIOD_M2)
    v2 = compute_smma(hl2, PERIOD_V2)

    n = len(hl2)
    states: List[LarssonState] = []
    for i in range(n):
        states.append(evaluate_larsson_state(v1[i], m1[i], m2[i], v2[i]))

    return v1, m1, m2, v2, states


def update_incremental_smma(prev_smma: float, new_src: float, length: int) -> float:
    """Updates a single SMMA value when a new candle arrives."""
    return (prev_smma * (length - 1) + new_src) / length
