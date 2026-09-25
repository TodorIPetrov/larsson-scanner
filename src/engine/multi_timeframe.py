"""
Multi-Timeframe Confluence Engine for Larsson Line Scanner.

Computes Larsson ribbon state across 4H, Daily, and Weekly timeframes and
derives a concise confluence classification plus a numeric score.

Design decisions:
- The weekly / 4h data are optional; when absent the timeframe is treated as
  NEUTRAL with bars_in_state=0 and excluded from scoring.
- `compute_multi_timeframe_ribbons` is the single public entry point and is
  intentionally pure (no I/O, no side-effects) so it is trivially testable.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from src.engine.smma import compute_larsson_series, LarssonState, MIN_WARMUP_CANDLES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_ribbon(
    highs: np.ndarray,
    lows: np.ndarray,
) -> Tuple[LarssonState, int]:
    """Compute latest state and bars_in_state for a single timeframe.

    Returns (state, bars_in_state). bars_in_state is the count of consecutive
    bars where the ribbon has held its current state (0 means entered this bar).
    """
    if len(highs) < MIN_WARMUP_CANDLES:
        return LarssonState.NEUTRAL, 0

    _, _, _, _, states = compute_larsson_series(highs, lows)
    if not states:
        return LarssonState.NEUTRAL, 0

    current_state = states[-1]
    bars = 0
    for i in range(len(states) - 1, 0, -1):
        if states[i] == current_state and states[i - 1] != current_state:
            bars = (len(states) - 1) - i
            break
    else:
        # State has held since the beginning of the data
        bars = len(states) - 1

    return current_state, bars


def _derive_confluence(
    h4_state: LarssonState,
    daily_state: LarssonState,
    weekly_state: LarssonState,
    h4_available: bool,
    weekly_available: bool,
) -> Tuple[str, int]:
    """Derive a named confluence label and a 0-3 gold-count score.

    Only available timeframes contribute to the score. The label names are
    deterministic so the frontend can filter on them.
    """
    gold_states = []
    blue_states = []

    if h4_available:
        gold_states.append(h4_state == LarssonState.GOLD)
        blue_states.append(h4_state == LarssonState.BLUE)
    gold_states.append(daily_state == LarssonState.GOLD)
    blue_states.append(daily_state == LarssonState.BLUE)
    if weekly_available:
        gold_states.append(weekly_state == LarssonState.GOLD)
        blue_states.append(weekly_state == LarssonState.BLUE)

    gold_count = sum(gold_states)
    blue_count = sum(blue_states)
    total = len(gold_states)  # number of available timeframes

    # --- Confluence labelling logic ---
    if total == 3:
        if gold_count == 3:
            return "TRIPLE_GOLD", 3
        if blue_count == 3:
            return "TRIPLE_BLUE", 0
        # Two-of-three golds
        if gold_count == 2:
            if h4_available and daily_state == LarssonState.GOLD and h4_state == LarssonState.GOLD:
                return "DOUBLE_GOLD_DAILY_4H", 2
            if weekly_available and daily_state == LarssonState.GOLD and weekly_state == LarssonState.GOLD:
                return "DOUBLE_GOLD_DAILY_WEEKLY", 2
            # 4H + Weekly gold, daily not
            return "DOUBLE_GOLD_4H_WEEKLY", 2
        # Two-of-three blues
        if blue_count == 2:
            if h4_available and daily_state == LarssonState.BLUE and h4_state == LarssonState.BLUE:
                return "DOUBLE_BLUE_DAILY_4H", 0
            if weekly_available and daily_state == LarssonState.BLUE and weekly_state == LarssonState.BLUE:
                return "DOUBLE_BLUE_DAILY_WEEKLY", 0
            return "DOUBLE_BLUE_4H_WEEKLY", 0
        return "MIXED", gold_count

    if total == 2:
        # Only daily is always present; the other is either 4H or weekly
        if gold_count == 2:
            label = "DOUBLE_GOLD_DAILY_4H" if h4_available else "DOUBLE_GOLD_DAILY_WEEKLY"
            return label, 2
        if blue_count == 2:
            label = "DOUBLE_BLUE_DAILY_4H" if h4_available else "DOUBLE_BLUE_DAILY_WEEKLY"
            return label, 0
        return "MIXED", gold_count

    # Only daily available
    if daily_state == LarssonState.GOLD:
        return "DAILY_GOLD_ONLY", 1
    if daily_state == LarssonState.BLUE:
        return "DAILY_BLUE_ONLY", 0
    return "MIXED", 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_multi_timeframe_ribbons(
    symbol: str,
    daily_highs: np.ndarray,
    daily_lows: np.ndarray,
    weekly_highs: Optional[np.ndarray] = None,
    weekly_lows: Optional[np.ndarray] = None,
    h4_highs: Optional[np.ndarray] = None,
    h4_lows: Optional[np.ndarray] = None,
) -> Dict:
    """Compute multi-timeframe Larsson ribbon confluence for a symbol.

    Parameters
    ----------
    symbol:
        Ticker / symbol name (informational, not used in computation).
    daily_highs / daily_lows:
        Numpy arrays of daily High / Low prices (required).
    weekly_highs / weekly_lows:
        Optional Weekly High / Low arrays.
    h4_highs / h4_lows:
        Optional 4-Hour High / Low arrays.

    Returns
    -------
    dict with structure::

        {
            '4h':     {'state': 'GOLD'|'BLUE'|'NEUTRAL', 'bars_in_state': N},
            'daily':  {'state': ..., 'bars_in_state': N},
            'weekly': {'state': ..., 'bars_in_state': N},
            'confluence': 'TRIPLE_GOLD' | 'DOUBLE_GOLD_DAILY_4H' | ...,
            'confluence_score': 0-3,  # count of GOLD timeframes
        }
    """
    # Daily (always required)
    daily_state, daily_bars = _compute_ribbon(daily_highs, daily_lows)

    # 4H (optional)
    h4_available = h4_highs is not None and h4_lows is not None and len(h4_highs) >= MIN_WARMUP_CANDLES
    if h4_available:
        h4_state, h4_bars = _compute_ribbon(h4_highs, h4_lows)  # type: ignore[arg-type]
    else:
        h4_state, h4_bars = LarssonState.NEUTRAL, 0

    # Weekly (optional)
    weekly_available = weekly_highs is not None and weekly_lows is not None and len(weekly_highs) >= MIN_WARMUP_CANDLES
    if weekly_available:
        weekly_state, weekly_bars = _compute_ribbon(weekly_highs, weekly_lows)  # type: ignore[arg-type]
    else:
        weekly_state, weekly_bars = LarssonState.NEUTRAL, 0

    confluence, score = _derive_confluence(
        h4_state=h4_state,
        daily_state=daily_state,
        weekly_state=weekly_state,
        h4_available=h4_available,
        weekly_available=weekly_available,
    )

    return {
        "4h": {
            "state": h4_state.value,
            "bars_in_state": h4_bars,
            "available": h4_available,
        },
        "daily": {
            "state": daily_state.value,
            "bars_in_state": daily_bars,
            "available": True,
        },
        "weekly": {
            "state": weekly_state.value,
            "bars_in_state": weekly_bars,
            "available": weekly_available,
        },
        "confluence": confluence,
        "confluence_score": score,
    }
