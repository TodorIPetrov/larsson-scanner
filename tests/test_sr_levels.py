"""
Tests for Support & Resistance (S/R) Mathematical Engine.
"""

import numpy as np
import pytest

from src.engine.sr_levels import (
    Pivot,
    SRZone,
    SRAnalysis,
    compute_atr,
    find_swing_pivots,
    cluster_sr_zones,
    analyze_sr_levels,
)


def test_compute_atr_basic():
    # Synthetic series with constant range 10
    n = 30
    high = np.arange(100, 100 + n, dtype=np.float64) + 5
    low = np.arange(100, 100 + n, dtype=np.float64) - 5
    close = np.arange(100, 100 + n, dtype=np.float64)

    atr = compute_atr(high, low, close, period=14)
    assert len(atr) == n
    assert not np.isnan(atr[-1])
    assert atr[-1] > 0
    # True range should be approx 10
    assert abs(atr[-1] - 10.0) < 1.0


def test_compute_atr_short_array():
    high = np.array([105.0, 110.0, 108.0])
    low = np.array([95.0, 100.0, 98.0])
    close = np.array([100.0, 105.0, 102.0])

    atr = compute_atr(high, low, close, period=14)
    assert len(atr) == 3
    assert not np.any(np.isnan(atr))
    assert atr[-1] > 0


def test_find_swing_pivots_clean_peak_trough():
    # 21 bars with a clear peak at bar 10 and trough at bar 5
    prices = np.array([
        100, 101, 102, 101, 98, 95, 98, 102, 105, 108,
        115,  # Peak at idx 10
        110, 107, 104, 102, 100, 98, 97, 96, 95, 94
    ], dtype=np.float64)

    high = prices + 1.0
    low = prices - 1.0

    high_pivots, low_pivots = find_swing_pivots(high, low, left_bars=3, right_bars=3)

    assert any(p.index == 10 and p.price == 116.0 for p in high_pivots)
    assert any(p.index == 5 and p.price == 94.0 for p in low_pivots)


def test_cluster_sr_zones():
    # 3 pivots near 100 and 2 pivots near 150
    pivots = [
        Pivot(index=10, price=100.0, pivot_type="HIGH"),
        Pivot(index=25, price=100.5, pivot_type="HIGH"),
        Pivot(index=40, price=99.8, pivot_type="LOW"),
        Pivot(index=50, price=150.0, pivot_type="HIGH"),
        Pivot(index=70, price=150.2, pivot_type="HIGH"),
    ]

    zones = cluster_sr_zones(
        pivots=pivots,
        current_atr=2.0,
        total_bars=100,
        tolerance_atr=0.5,  # tolerance = 1.0
    )

    assert len(zones) == 2
    # First zone should be around 100 with 3 touches
    assert zones[0].touches == 3
    assert abs(zones[0].core_price - 100.0) <= 0.5
    assert zones[0].zone_type == "BOTH"

    # Second zone should be around 150 with 2 touches
    assert zones[1].touches == 2
    assert abs(zones[1].core_price - 150.1) <= 0.5
    assert zones[1].zone_type == "RESISTANCE"


def test_analyze_sr_levels_comprehensive():
    # Generate an oscillatory price series that bounces between 100 and 120
    t = np.linspace(0, 4 * np.pi, 80)
    base = 110 + 10 * np.sin(t)
    high = base + 1.5
    low = base - 1.5
    close = base

    # 1. Price in middle of range (110)
    analysis = analyze_sr_levels(high, low, close, current_price=110.0, left_bars=4, right_bars=4)
    assert analysis.s1 is not None
    assert analysis.r1 is not None
    assert analysis.s1 < 110.0
    assert analysis.r1 > 110.0
    assert analysis.s1_dist_pct is not None and analysis.s1_dist_pct > 0
    assert analysis.r1_dist_pct is not None and analysis.r1_dist_pct > 0
    assert len(analysis.zones) >= 2

    # 2. Price near resistance (e.g. 120.5)
    analysis_res = analyze_sr_levels(high, low, close, current_price=120.5, left_bars=4, right_bars=4)
    # R1 might be very close or in breakout
    assert analysis_res.context_flag in ["NEAR_RESISTANCE", "BREAKOUT_ABOVE"]

    # 3. Price near support (e.g. 99.5)
    analysis_sup = analyze_sr_levels(high, low, close, current_price=99.5, left_bars=4, right_bars=4)
    assert analysis_sup.context_flag in ["NEAR_SUPPORT", "BREAKDOWN_BELOW"]


def test_analyze_sr_levels_edge_cases():
    # Flat line
    high = np.full(50, 100.0)
    low = np.full(50, 99.0)
    close = np.full(50, 99.5)

    analysis = analyze_sr_levels(high, low, close, current_price=99.5)
    assert analysis.current_price == 99.5
    assert analysis.atr > 0
