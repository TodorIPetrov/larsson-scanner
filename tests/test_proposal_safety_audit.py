"""
Audit Verification Test Suite: Trade Proposal Safety & Liquidation Hardening.
Tests liquidation price vs. stop-loss checks, gap safety thresholds (>= 10%),
and risk-to-reward ratio integrity.
"""

import pytest
from src.engine.trade_suggestions import (
    calculate_leverage_matrix,
    generate_trade_suggestion,
)


def test_leverage_matrix_fatal_liquidation_trap():
    """
    Simulates NEAR / ENA failure scenario where 3x liquidation hits BEFORE the stop-loss.
    Entry: $4.80, SL: $2.99 (drop of ~37.7%).
    At 3x leverage, liquidation is ~ entry * (1 - 1/3 + 0.005) = $3.224.
    Since Stop-Loss ($2.99) is below liquidation ($3.224), the trader is liquidated before SL!
    """
    matrix = calculate_leverage_matrix(
        entry_price=4.80,
        stop_loss=2.99,
        direction="LONG",
    )

    lev_3x = next(row for row in matrix if row["leverage"] == 3)
    
    # Must flag as unsafe
    assert lev_3x["is_safe"] is False
    assert lev_3x["liquidation_price"] > 2.99  # Liquidation triggers above Stop Loss
    assert lev_3x["liq_gap_pct"] < 0    # Gap is negative (catastrophic)
    assert "FATAL" in lev_3x["safety_warning"] or "Stop-Loss" in lev_3x["safety_warning"]


def test_leverage_matrix_thin_buffer_warning():
    """
    Tests scenario where liquidation is below SL, but buffer is under 10%.
    Entry: $100, SL: $70 (30% drop).
    At 2x leverage, liquidation is 100 * (1 - 0.5 + 0.005) = $50.50.
    Gap: (70 - 50.50) / 100 = 19.5% (Safe).
    At 3x leverage, liquidation is 100 * (1 - 0.3333 + 0.005) = $67.17.
    Gap: (70 - 67.17) / 100 = 2.83% (< 10% threshold -> Unsafe thin buffer).
    """
    matrix = calculate_leverage_matrix(
        entry_price=100.0,
        stop_loss=70.0,
        direction="LONG",
    )

    lev_3x = next(row for row in matrix if row["leverage"] == 3)
    assert lev_3x["is_safe"] is False
    assert 0 < lev_3x["liq_gap_pct"] < 10.0
    assert "buffer" in lev_3x["safety_warning"].lower() or "10%" in lev_3x["safety_warning"]

    lev_2x = next(row for row in matrix if row["leverage"] == 2)
    assert lev_2x["is_safe"] is True
    assert lev_2x["liq_gap_pct"] >= 10.0
    assert lev_2x["safety_warning"] == ""


def test_leverage_matrix_safe_tight_stop():
    """
    Tight institutional stop loss (5% drop).
    Entry: $100, SL: $95.
    At 2x (liq $50.50) and 3x (liq $67.17), stop loss is well protected with > 10% gap.
    """
    matrix = calculate_leverage_matrix(
        entry_price=100.0,
        stop_loss=95.0,
        direction="LONG",
    )

    for row in matrix:
        if row["leverage"] > 1:
            assert row["is_safe"] is True
            assert row["liq_gap_pct"] >= 10.0
            assert row["safety_warning"] == ""


def test_leverage_matrix_short_fatal_trap():
    """
    Short position where stop loss is above entry, and liquidation price is below stop loss.
    Entry: 100, SL: 140.
    At 3x short, liq price is ~ 100 * (1 + 0.3333 - 0.005) = ~132.83.
    Stop loss is 140, so liquidation hits before stop!
    """
    matrix = calculate_leverage_matrix(
        entry_price=100.0,
        stop_loss=140.0,
        direction="SHORT",
    )

    lev_3x = next(row for row in matrix if row["leverage"] == 3)
    assert lev_3x["is_safe"] is False
    assert lev_3x["liquidation_price"] < 140.0
    assert "FATAL" in lev_3x["safety_warning"] or "Stop-Loss" in lev_3x["safety_warning"]


def test_trade_suggestion_minimum_rr_ratio():
    """
    Verifies that trade suggestions generate setups adhering to favorable R:R.
    """
    suggestion = generate_trade_suggestion(
        current_price=69000.0,
        state="GOLD",
        v1=72000.0,
        m1=71000.0,
        m2=70000.0,
        v2=68500.0,
        spread_pct=1.2,
        atr=2000.0,
        s1=67000.0,
        s1_lower=66800.0,
        s1_touches=3,
        r1=82500.0,
        context_flag="NEAR_SUPPORT",
        timeframe="1D",
    )

    assert suggestion.action == "SPOT_BUY"
    assert suggestion.rr_ratio >= 1.8
    assert suggestion.rr_ratio >= 1.8
