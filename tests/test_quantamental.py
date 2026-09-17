"""
Tests for Quantamental Fusion Engine.
Verifies loading of institutional equity valuation (verdicts.json),
multi-asset memos (crypto, commodities, macro), and quantamental trade suggestion rules.
"""

import pytest
from src.engine.quantamental import (
    FundamentalProfile,
    QuantamentalRegistry,
    get_fundamental_profile,
)
from src.engine.trade_suggestions import generate_trade_suggestion


def test_quantamental_registry_loading():
    registry = QuantamentalRegistry.get_instance()
    assert len(registry.profiles) > 50

    # Verify multi-asset coverage
    btc = registry.get_profile("BTCUSDT")
    assert btc is not None
    assert btc.verdict == "STRONG BUY"
    assert btc.moat == "Wide"
    assert btc.is_bullish is True
    assert btc.fair_value == 110000.0

    gold = registry.get_profile("GC=F")
    assert gold is not None
    assert gold.verdict == "STRONG BUY"
    assert gold.is_bullish is True

    # Verify equity from verdicts.json
    deck = registry.get_profile("DECK")
    assert deck is not None
    assert "STRONG BUY" in deck.verdict
    assert deck.moat == "Wide"
    assert deck.fair_value > 100.0
    assert deck.z_score > 2.99


def test_ticker_resolution_exchange_prefixes():
    # NASDAQ:AAPL -> AAPL
    aapl = get_fundamental_profile("NASDAQ:AAPL")
    assert aapl is not None
    assert aapl.ticker == "AAPL"
    assert "REDUCE" in aapl.verdict
    assert aapl.is_bearish_or_distressed is True

    # BINANCE:BTCUSDT -> BTCUSDT
    btc = get_fundamental_profile("BINANCE:BTCUSDT")
    assert btc is not None
    assert btc.ticker == "BTCUSDT"


def test_quantamental_alpha_buy_setup():
    deck_profile = get_fundamental_profile("DECK")
    assert deck_profile is not None

    suggestion = generate_trade_suggestion(
        current_price=78.0,
        state="GOLD",
        v1=82.0,
        m1=80.0,
        m2=77.0,
        v2=75.0,
        spread_pct=8.5,
        atr=2.5,
        s1=76.0,
        s1_lower=74.5,
        s1_touches=3,
        r1=95.0,
        r1_lower=93.0,
        context_flag="NEAR_SUPPORT",
        fund_profile=deck_profile,
    )

    assert suggestion.action == "SPOT_BUY"
    assert suggestion.setup_type == "QUANTAMENTAL_ALPHA_BUY"
    assert suggestion.quantamental_tag == "INSTITUTIONAL_ALPHA"
    assert suggestion.tier == "A+"
    assert suggestion.score >= 85
    # TP2 should stretch to DCF Fair Value ($175.36)
    assert suggestion.tp2 == pytest.approx(deck_profile.fair_value, 0.01)
    assert "ИНСТИТУЦИОНАЛЕН АЛФА ВХОД" in suggestion.reason_bg


def test_value_trap_guard_in_downtrend():
    # Fundamentally undervalued (STRONG BUY), but technical state is BLUE
    deck_profile = get_fundamental_profile("DECK")
    assert deck_profile is not None
    assert deck_profile.is_bullish is True

    suggestion = generate_trade_suggestion(
        current_price=75.0,
        state="BLUE",
        v1=80.0,
        m1=82.0,
        m2=84.0,
        v2=86.0,
        spread_pct=-7.0,
        atr=2.0,
        s1=78.0,
        fund_profile=deck_profile,
    )

    # Must NOT generate a buy signal!
    assert suggestion.action == "WAIT"
    assert suggestion.setup_type == "VALUE_TRAP_WARNING"
    assert suggestion.quantamental_tag == "VALUE_TRAP_RISK"
    assert suggestion.tier == "NONE"
    assert "ВАЛУАЦИОНЕН КАПАН" in suggestion.reason_bg


def test_speculative_momentum_cap_on_weak_fundamentals():
    # Dogecoin has REDUCE verdict / weak balance sheet
    doge_profile = get_fundamental_profile("DOGEUSDT")
    assert doge_profile is not None
    assert doge_profile.is_bearish_or_distressed is True

    suggestion = generate_trade_suggestion(
        current_price=0.08,
        state="GOLD",
        v1=0.082,
        m1=0.078,
        m2=0.075,
        v2=0.072,
        spread_pct=13.0,
        atr=0.004,
        s1=0.075,
        s1_lower=0.074,
        s1_touches=3,
        r1=0.12,
        r1_lower=0.115,
        context_flag="NEAR_SUPPORT",
        fund_profile=doge_profile,
    )

    assert suggestion.action == "SPOT_BUY"
    assert suggestion.setup_type == "SPECULATIVE_PULLBACK_BUY"
    assert suggestion.quantamental_tag == "SPECULATIVE_MOMENTUM"
    # Even with high technical points, tier MUST be capped at B
    assert suggestion.tier == "B"
    assert "СПЕКУЛАТИВЕН" in suggestion.reason_bg


def test_core_quality_hold_accumulation():
    # Microsoft is HOLD / ACCUMULATE ON PULLBACK
    msft_profile = get_fundamental_profile("MSFT")
    assert msft_profile is not None
    assert msft_profile.is_hold is True

    suggestion = generate_trade_suggestion(
        current_price=470.0,
        state="GOLD",
        v1=480.0,
        m1=475.0,
        m2=465.0,
        v2=460.0,
        spread_pct=4.3,
        atr=10.0,
        s1=465.0,
        s1_lower=462.0,
        s1_touches=2,
        r1=520.0,
        r1_lower=515.0,
        context_flag="NEAR_SUPPORT",
        fund_profile=msft_profile,
    )

    assert suggestion.action == "SPOT_BUY"
    assert suggestion.setup_type == "QUALITY_HOLD_ACCUMULATION"
    assert suggestion.quantamental_tag == "CORE_QUALITY_HOLD"
    assert "ЕЛИТЕН ЛИДЕР" in suggestion.reason_bg
