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


def test_max_allowed_leverage_rules():
    from src.engine.asset_profiles import get_max_allowed_leverage
    from src.engine.trade_suggestions import calculate_leverage_matrix

    # Tier S with high score and low ATR% qualifies for 3x
    lev_btc = get_max_allowed_leverage(
        ticker="BTCUSDT",
        asset_class="crypto",
        score=85,
        tier="A+",
        atr_pct=3.0,
        direction="LONG",
    )
    assert lev_btc == 3

    # Tier A stock with solid score qualifies for 3x
    lev_aapl = get_max_allowed_leverage(
        ticker="AAPL",
        asset_class="us_stocks",
        score=80,
        tier="A",
        atr_pct=2.5,
        direction="LONG",
    )
    assert lev_aapl == 3

    # Tier B qualifies for 2x max
    lev_tier_b = get_max_allowed_leverage(
        ticker="NEARUSDT",
        asset_class="crypto",
        score=70,
        tier="B",
        atr_pct=4.0,
        direction="LONG",
    )
    assert lev_tier_b == 2

    # High volatility asset (ATR% >= 6.5%) is restricted to 1x
    lev_volatile = get_max_allowed_leverage(
        ticker="MEMEUSDT",
        asset_class="crypto",
        score=80,
        tier="A",
        atr_pct=7.5,
        direction="LONG",
    )
    assert lev_volatile == 1

    # Tier C is restricted to 1x
    lev_tier_c = get_max_allowed_leverage(
        ticker="SHIBUSDT",
        asset_class="crypto",
        score=50,
        tier="NONE",
        atr_pct=3.0,
        direction="LONG",
    )
    assert lev_tier_c == 1

    # Test leverage matrix calculation
    matrix_long = calculate_leverage_matrix(
        entry_price=60000.0,
        stop_loss=57000.0,
        position_size_usd=300.0,
        max_leverage=3,
        direction="LONG",
    )
    lev_map = {m["leverage"]: m for m in matrix_long}
    assert 1 in lev_map
    assert 2 in lev_map
    assert 3 in lev_map

    # 1x Spot
    assert lev_map[1]["margin_usd"] == 300.0
    assert lev_map[1]["liquidation_price"] is None

    # 2x Long
    assert lev_map[2]["margin_usd"] == 150.0
    assert lev_map[2]["liquidation_price"] < 57000.0  # liquidation far below SL!

    # 3x Long
    assert lev_map[3]["margin_usd"] == 100.0
    # Liquidation price for 3x: 60000 * (1 - 1/3 + 0.005) = 60000 * 0.671667 = ~40300
    assert lev_map[3]["liquidation_price"] < 45000.0

    # Short leverage matrix
    matrix_short = calculate_leverage_matrix(
        entry_price=3000.0,
        stop_loss=3150.0,
        position_size_usd=200.0,
        max_leverage=2,
        direction="SHORT",
    )
    short_map = {m["leverage"]: m for m in matrix_short}
    assert 1 in short_map
    assert 2 in short_map
    assert 3 not in short_map
    assert short_map[2]["margin_usd"] == 100.0
    # Liquidation price for 2x short: 3000 * (1 + 0.5 - 0.005) = 3000 * 1.495 = 4485
    assert short_map[2]["liquidation_price"] > 3150.0
