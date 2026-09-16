"""
Tests for Trade Suggestions Engine.
Verifies all setup archetypes, SL/TP pricing, R:R calculation, and quality tier assignments.
"""

import pytest
from src.engine.trade_suggestions import (
    TradeSuggestion,
    calculate_confluence_score,
    generate_trade_suggestion,
)


def test_confluence_scoring():
    # Prime institutional setup
    score, tier = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=3,
        spread_expanding=True,
        rr_ratio=2.6,
    )
    assert score >= 85
    assert tier == "A+"

    # Moderate setup
    score_b, tier_b = calculate_confluence_score(
        is_mtf_aligned=False,
        near_support=True,
        s1_touches=1,
        spread_expanding=False,
        rr_ratio=1.9,
    )
    assert score_b < 85
    assert tier_b in ["A", "B"]


def test_pullback_value_buy():
    # Price pulls back to S1 at 67,000, R1 is 82,500, ribbon v2 is 68,000
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
    assert suggestion.direction == "LONG"
    assert suggestion.setup_type == "PULLBACK_VALUE_BUY"
    assert suggestion.entry_price == 69000.0
    # SL should be below min(s1_lower, v2) - 0.5*atr = 66800 - 1000 = 65800
    assert suggestion.stop_loss == 65800.0
    assert suggestion.tp1 == 82500.0
    assert suggestion.rr_ratio > 2.0
    assert suggestion.tier in ["A+", "A"]


def test_take_profit_near_resistance():
    # Price is right under R1 (82,000 when R1 is 82,500)
    suggestion = generate_trade_suggestion(
        current_price=82000.0,
        state="GOLD",
        v1=78000.0,
        m1=76000.0,
        m2=74000.0,
        v2=72000.0,
        spread_pct=1.5,
        atr=2000.0,
        s1=67000.0,
        r1=82500.0,
        context_flag="NEAR_RESISTANCE",
        timeframe="1D",
    )

    assert suggestion.action == "TAKE_PROFIT"
    assert suggestion.direction == "NEUTRAL"
    assert suggestion.setup_type == "TAKE_PROFIT_SELL"
    assert "съпротива R1" in suggestion.reason_bg or "R1" in suggestion.reason_bg


def test_breakout_buy():
    # Price broke above all resistances into ATH Price Discovery
    suggestion = generate_trade_suggestion(
        current_price=90000.0,
        state="GOLD",
        v1=85000.0,
        m1=83000.0,
        m2=81000.0,
        v2=79000.0,
        spread_pct=2.0,
        atr=2500.0,
        s1=82500.0,
        r1=None,
        context_flag="BREAKOUT_ABOVE",
        timeframe="1D",
    )

    assert suggestion.action == "SPOT_BUY"
    assert suggestion.direction == "LONG"
    assert suggestion.setup_type == "BREAKOUT_BUY"
    assert suggestion.tp1 > 90000.0
    assert suggestion.stop_loss < 90000.0


def test_structural_exit():
    # Trend broke down to BLUE and fell below S1
    suggestion = generate_trade_suggestion(
        current_price=64000.0,
        state="BLUE",
        v1=68000.0,
        m1=69000.0,
        m2=70000.0,
        v2=71000.0,
        spread_pct=-1.5,
        atr=2000.0,
        s1=67000.0,
        r1=75000.0,
        context_flag="BREAKDOWN_BELOW",
        timeframe="1D",
    )

    assert suggestion.action == "EXIT_PROTECT"
    assert suggestion.direction == "EXIT"
    assert suggestion.setup_type == "STRUCTURAL_EXIT"


def test_wait_when_rr_too_low():
    # Price is mid-range, close to R1 so R:R is poor (< 1.8)
    suggestion = generate_trade_suggestion(
        current_price=79000.0,
        state="GOLD",
        v1=75000.0,
        m1=73000.0,
        m2=71000.0,
        v2=69000.0,
        spread_pct=1.0,
        atr=2000.0,
        s1=67000.0,
        r1=81000.0,  # only 2,000 reward vs 11,000 risk!
        context_flag="IN_VALUE_RANGE",
        timeframe="1D",
    )

    assert suggestion.action == "WAIT"
    assert suggestion.setup_type == "WAIT_FOR_SETUP"
