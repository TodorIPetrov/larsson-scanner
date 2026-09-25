"""
Tests for src/engine/multi_timeframe.py

Covers:
- Triple Gold confluence
- Triple Blue confluence
- Mixed states (e.g. Daily + 4H Gold, Weekly Blue)
- Confluence score calculation (0 to 3)
- Graceful handling of missing optional timeframes (weekly / 4h None or insufficient candles)
- Insufficient daily candles fallback
"""

import numpy as np
import pytest

from src.engine.multi_timeframe import compute_multi_timeframe_ribbons
from src.engine.smma import LarssonState, MIN_WARMUP_CANDLES


def _make_bullish_candles(n: int = 200, base: float = 100.0):
    """Generate steadily rising candles where v1 >= m1 >= m2 >= v2 (GOLD)."""
    t = np.arange(n, dtype=float)
    closes = base + t * 2.0
    highs = closes + 1.0
    lows = closes - 1.0
    return highs, lows


def _make_bearish_candles(n: int = 200, base: float = 600.0):
    """Generate steadily falling candles where v1 < m1 < m2 < v2 (BLUE)."""
    t = np.arange(n, dtype=float)
    closes = base - t * 2.0
    highs = closes + 1.0
    lows = closes - 1.0
    return highs, lows


def _make_choppy_candles(n: int = 200, base: float = 100.0):
    """Generate alternating candles causing entangled ribbon (NEUTRAL)."""
    t = np.arange(n, dtype=float)
    closes = base + np.sin(t * 0.8) * 3.0
    highs = closes + 1.5
    lows = closes - 1.5
    return highs, lows


def test_triple_gold():
    d_h, d_l = _make_bullish_candles(200)
    w_h, w_l = _make_bullish_candles(200)
    h4_h, h4_l = _make_bullish_candles(200)

    res = compute_multi_timeframe_ribbons(
        "BTCUSDT",
        daily_highs=d_h,
        daily_lows=d_l,
        weekly_highs=w_h,
        weekly_lows=w_l,
        h4_highs=h4_h,
        h4_lows=h4_l,
    )

    assert res["daily"]["state"] == LarssonState.GOLD.value
    assert res["weekly"]["state"] == LarssonState.GOLD.value
    assert res["4h"]["state"] == LarssonState.GOLD.value
    assert res["confluence"] == "TRIPLE_GOLD"
    assert res["confluence_score"] == 3


def test_triple_blue():
    d_h, d_l = _make_bearish_candles(200)
    w_h, w_l = _make_bearish_candles(200)
    h4_h, h4_l = _make_bearish_candles(200)

    res = compute_multi_timeframe_ribbons(
        "ETHUSDT",
        daily_highs=d_h,
        daily_lows=d_l,
        weekly_highs=w_h,
        weekly_lows=w_l,
        h4_highs=h4_h,
        h4_lows=h4_l,
    )

    assert res["daily"]["state"] == LarssonState.BLUE.value
    assert res["weekly"]["state"] == LarssonState.BLUE.value
    assert res["4h"]["state"] == LarssonState.BLUE.value
    assert res["confluence"] == "TRIPLE_BLUE"
    assert res["confluence_score"] == 0


def test_double_gold_daily_4h():
    d_h, d_l = _make_bullish_candles(200)
    w_h, w_l = _make_bearish_candles(200)
    h4_h, h4_l = _make_bullish_candles(200)

    res = compute_multi_timeframe_ribbons(
        "SOLUSDT",
        daily_highs=d_h,
        daily_lows=d_l,
        weekly_highs=w_h,
        weekly_lows=w_l,
        h4_highs=h4_h,
        h4_lows=h4_l,
    )

    assert res["daily"]["state"] == LarssonState.GOLD.value
    assert res["4h"]["state"] == LarssonState.GOLD.value
    assert res["weekly"]["state"] == LarssonState.BLUE.value
    assert res["confluence"] == "DOUBLE_GOLD_DAILY_4H"
    assert res["confluence_score"] == 2


def test_missing_optional_timeframes():
    d_h, d_l = _make_bullish_candles(200)

    res = compute_multi_timeframe_ribbons(
        "AAPL",
        daily_highs=d_h,
        daily_lows=d_l,
        weekly_highs=None,
        weekly_lows=None,
        h4_highs=None,
        h4_lows=None,
    )

    assert res["daily"]["state"] == LarssonState.GOLD.value
    assert res["weekly"]["available"] is False
    assert res["4h"]["available"] is False
    assert res["confluence"] == "DAILY_GOLD_ONLY"
    assert res["confluence_score"] == 1


def test_short_candles_handled_gracefully():
    # Only 5 candles (less than MIN_WARMUP_CANDLES 35)
    d_h = np.array([10, 11, 12, 13, 14], dtype=float)
    d_l = np.array([9, 10, 11, 12, 13], dtype=float)

    res = compute_multi_timeframe_ribbons(
        "NEW_COIN",
        daily_highs=d_h,
        daily_lows=d_l,
    )

    assert res["daily"]["state"] == LarssonState.NEUTRAL.value
    assert res["confluence_score"] == 0
